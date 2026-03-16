"""
agents/llm.py
LLM Router com Fallback Multi-Provider (Custo Zero)

Hierarquia de Fallback:
  1. Groq Cloud — Primary (llama-3.3-70b para tarefas complexas, llama-3.1-8b para rápidas)
  2. Google Gemini — Secondary (gemini-2.0-flash via GEMINI_API_KEY — free tier 15 req/min)
  3. OpenRouter — Tertiary (OPENROUTER_API_KEY free tier — modelos open-source)
  4. Modo Degradado — Final (resposta estruturada mínima sem LLM, apenas lógica determinística)
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from core.config import Config
from utils.logger import setup_logger
from typing import Optional, List, Dict, Any
import asyncio
import hashlib
import json
import os
import time

# Exceptions customizadas para controle de fallback
class RateLimitError(Exception):
    """Erro de rate limit do provider."""
    pass

class ServiceUnavailableError(Exception):
    """Serviço do provider indisponível."""
    pass


class LLMProvider:
    """Classe base para providers de LLM."""
    
    def __init__(self, name: str, api_key: Optional[str] = None):
        self.name = name
        self.api_key = api_key
        self.logger = setup_logger(f"LLMProvider.{name}")
    
    async def complete(self, prompt: str, model: str = None, **kwargs) -> str:
        """
        Executa completção de texto.
        
        Args:
            prompt: Prompt de entrada
            model: Modelo específico (opcional)
            **kwargs: Argumentos adicionais (temperature, max_tokens, etc.)
        
        Returns:
            Resposta de texto do modelo
        
        Raises:
            RateLimitError: Quando atinge limite de requisições
            ServiceUnavailableError: Quando o serviço está indisponível
        """
        raise NotImplementedError
    
    def is_available(self) -> bool:
        """Verifica se o provider está configurado e disponível."""
        return bool(self.api_key and self.api_key not in ["", "COLE_O_SEU_TOKEN_AQUI", None])


class GroqProvider(LLMProvider):
    """Provider primário: Groq Cloud (Llama 3.3, Llama 3.1, Gemma 2)."""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__("Groq", api_key)
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization do cliente Groq."""
        if self._client is None:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client
    
    async def complete(self, prompt: str, model: str = None, **kwargs) -> str:
        """
        Executa completção via Groq Cloud.
        
        Pool de modelos para rodízio em caso de rate limit:
        - llama-3.3-70b-versatile (complexo)
        - llama-3.1-8b-instant (rápido)
        - gemma2-9b-it (alternativa)
        """
        if not self.is_available():
            raise ServiceUnavailableError("Groq API key não configurada")
        
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)
        
        # Pool de modelos para fallback automático
        if model:
            models_pool = [model]
        else:
            task_type = kwargs.get("task_type", "general")
            if task_type == "complex":
                models_pool = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
            elif task_type == "fast":
                models_pool = ["llama-3.1-8b-instant", "gemma2-9b-it", "llama-3.3-70b-versatile"]
            elif task_type == "coding":
                models_pool = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            else:
                models_pool = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
        
        # Remove duplicatas mantendo ordem
        models_pool = list(dict.fromkeys(models_pool))
        
        last_error = None
        for current_model in models_pool:
            try:
                self.logger.info(f"[Groq] Tentando modelo: {current_model}")
                
                messages = [{"role": "user", "content": prompt}]
                
                completion = await self.client.chat.completions.create(
                    messages=messages,
                    model=current_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                
                response_text = completion.choices[0].message.content
                self.logger.info(f"[Groq] Sucesso com modelo: {current_model}")
                return response_text
                
            except Exception as e:
                err_msg = str(e)
                last_error = e
                
                # Verifica se é erro de rate limit ou indisponibilidade
                if "429" in err_msg or "rate_limit" in err_msg.lower() or "overloaded" in err_msg.lower():
                    self.logger.warning(f"[Groq] Rate limit no modelo {current_model}, tentando próximo...")
                    continue
                elif "503" in err_msg or "service unavailable" in err_msg.lower():
                    raise ServiceUnavailableError(f"Groq indisponível: {err_msg}")
                else:
                    self.logger.error(f"[Groq] Erro fatal: {err_msg}")
                    raise ServiceUnavailableError(f"Erro Groq: {err_msg}")
        
        # Todos os modelos do pool falharam
        raise RateLimitError(f"Todos os modelos Groq falharam. Último erro: {last_error}")


class GeminiProvider(LLMProvider):
    """Provider secundário: Google Gemini (free tier)."""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__("Gemini", api_key)
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization do cliente Gemini."""
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel('gemini-2.0-flash')
            except ImportError:
                self.logger.warning("google-generativeai não instalado. Instalando...")
                import subprocess
                subprocess.check_call(['pip', 'install', 'google-generativeai'])
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel('gemini-2.0-flash')
        return self._client
    
    async def complete(self, prompt: str, model: str = None, **kwargs) -> str:
        """Executa completção via Google Gemini."""
        if not self.is_available():
            raise ServiceUnavailableError("Gemini API key não configurada")
        
        try:
            self.logger.info("[Gemini] Enviando requisição...")
            
            # Gemini usa API síncrona, então executamos em thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.generate_content(prompt)
            )
            
            response_text = response.text
            self.logger.info("[Gemini] Resposta obtida com sucesso")
            return response_text
            
        except Exception as e:
            err_msg = str(e)
            
            if "429" in err_msg or "quota" in err_msg.lower() or "rate limit" in err_msg.lower():
                raise RateLimitError(f"Gemini rate limit: {err_msg}")
            elif "503" in err_msg or "service unavailable" in err_msg.lower():
                raise ServiceUnavailableError(f"Gemini indisponível: {err_msg}")
            else:
                self.logger.error(f"[Gemini] Erro: {err_msg}")
                raise ServiceUnavailableError(f"Erro Gemini: {err_msg}")


class OpenRouterProvider(LLMProvider):
    """Provider terciário: OpenRouter (modelos open-source gratuitos)."""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__("OpenRouter", api_key)
        self.base_url = "https://openrouter.ai/api/v1"
        self._session = None
    
    @property
    def session(self):
        """Lazy initialization da sessão HTTP."""
        if self._session is None:
            import httpx
            self._session = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/newjsouza/the-moon-ecosystem",
                    "X-Title": "The Moon Ecosystem"
                },
                timeout=30.0
            )
        return self._session
    
    async def complete(self, prompt: str, model: str = None, **kwargs) -> str:
        """Executa completção via OpenRouter."""
        if not self.is_available():
            raise ServiceUnavailableError("OpenRouter API key não configurada")
        
        # Modelos gratuitos/low-cost no OpenRouter
        if not model:
            task_type = kwargs.get("task_type", "general")
            if task_type == "coding":
                model = "meta-llama/llama-3.3-70b-instruct"
            elif task_type == "fast":
                model = "meta-llama/llama-3.1-8b-instruct"
            else:
                model = "meta-llama/llama-3.3-70b-instruct"
        
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)
        
        try:
            self.logger.info(f"[OpenRouter] Enviando requisição para modelo: {model}")
            
            response = await self.session.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            )
            
            if response.status_code == 429:
                raise RateLimitError("OpenRouter rate limit exceeded")
            elif response.status_code >= 500:
                raise ServiceUnavailableError(f"OpenRouter erro do servidor: {response.status_code}")
            
            response.raise_for_status()
            data = response.json()
            response_text = data["choices"][0]["message"]["content"]
            
            self.logger.info("[OpenRouter] Resposta obtida com sucesso")
            return response_text
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(f"OpenRouter rate limit: {e}")
            else:
                raise ServiceUnavailableError(f"OpenRouter HTTP error: {e}")
        except Exception as e:
            self.logger.error(f"[OpenRouter] Erro: {str(e)}")
            raise ServiceUnavailableError(f"Erro OpenRouter: {e}")


class LLMRouter:
    """
    Router de LLM com fallback em cascata multi-provider.
    
    Tenta cada provider na ordem de prioridade até obter sucesso.
    """
    
    def __init__(self, config: Optional[Config] = None):
        self.logger = setup_logger("LLMRouter")
        self._config = config or Config()
        
        # Inicializa providers com as API keys do .env
        groq_key = self._config.get("llm.api_key") or os.getenv("GROQ_API_KEY")
        gemini_key = self._config.get("gemini.api_key") or os.getenv("GEMINI_API_KEY")
        openrouter_key = self._config.get("openrouter.api_key") or os.getenv("OPENROUTER_API_KEY")
        
        self.providers: List[LLMProvider] = []
        
        # Adiciona providers na ordem de prioridade
        if groq_key:
            self.providers.append(GroqProvider(groq_key))
        else:
            self.logger.warning("Groq API key não configurada")
        
        if gemini_key:
            self.providers.append(GeminiProvider(gemini_key))
        else:
            self.logger.info("Gemini API key não configurada (fallback disponível)")
        
        if openrouter_key:
            self.providers.append(OpenRouterProvider(openrouter_key))
        else:
            self.logger.info("OpenRouter API key não configurada (fallback disponível)")
        
        # Contadores de uso para telemetria
        self.usage_stats: Dict[str, int] = {
            "groq": 0,
            "gemini": 0,
            "openrouter": 0,
            "degraded": 0
        }
    
    def _get_provider_order(self, task_type: str = "general") -> List[LLMProvider]:
        """
        Retorna lista de providers na ordem de tentativa.
        
        Args:
            task_type: Tipo de tarefa ("fast", "complex", "coding", "research")
        
        Returns:
            Lista de providers ordenada por prioridade
        """
        # Ordem padrão: providers configurados > modo degradado
        return self.providers.copy()
    
    async def complete(self, prompt: str, task_type: str = "general", **kwargs) -> str:
        """
        Tenta cada provider na ordem de fallback até obter sucesso.
        
        Args:
            prompt: Prompt de entrada
            task_type: Tipo de tarefa ("fast" | "complex" | "coding" | "research")
            **kwargs: Argumentos adicionais (model, temperature, max_tokens)
        
        Returns:
            Resposta do primeiro provider bem-sucedido ou resposta degradada
        """
        providers = self._get_provider_order(task_type)
        last_error = None
        
        if not providers:
            self.logger.warning("Nenhum provider configurado. Usando modo degradado.")
            return self._degraded_response(prompt, task_type)
        
        for provider in providers:
            try:
                self.logger.info(f"Tentando provider: {provider.name}")
                result = await provider.complete(prompt, task_type=task_type, **kwargs)
                
                # Registrar uso para telemetria
                await self._publish_usage(provider.name.lower(), task_type)
                self.usage_stats[provider.name.lower()] = self.usage_stats.get(provider.name.lower(), 0) + 1
                
                self.logger.info(f"Provider {provider.name} executado com sucesso")
                return result
                
            except (RateLimitError, ServiceUnavailableError) as e:
                last_error = e
                self.logger.warning(f"Provider {provider.name} indisponível: {e}")
                continue
            except Exception as e:
                last_error = e
                self.logger.error(f"Provider {provider.name} falhou com erro inesperado: {e}")
                continue
        
        # Todos os providers falharam - modo degradado
        self.logger.error(f"Todos os providers falharam. Último erro: {last_error}")
        self.usage_stats["degraded"] = self.usage_stats.get("degraded", 0) + 1
        await self._publish_usage("degraded", task_type)
        return self._degraded_response(prompt, task_type)
    
    def _degraded_response(self, prompt: str, task_type: str) -> str:
        """
        Gera resposta estruturada mínima sem LLM (modo degradado).
        
        Usa lógica determinística para fornecer resposta útil quando
        todos os providers de LLM estão indisponíveis.
        """
        self.logger.warning("Modo degradado ativado - retornando resposta determinística")
        
        # Respostas pré-definidas baseadas em palavras-chave
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in ["olá", "hello", "hi", "oi"]):
            return "Olá! Estou em modo degradado (todos os providers de LLM estão indisponíveis). Por favor, tente novamente em alguns instantes."
        
        if any(word in prompt_lower for word in ["ajuda", "help", "suporte"]):
            return "Modo degradado: Sistema operando com capacidade limitada. Providers de LLM indisponíveis no momento. Verifique as API keys no .env."
        
        if any(word in prompt_lower for word in ["status", "saúde", "health"]):
            return f"Status do LLM Router: {len(self.providers)} providers configurados. Modo degradado ativo."
        
        # Resposta genérica de fallback
        return (
            "[MODO DEGRADADO ATIVO]\n"
            "Todos os providers de LLM (Groq, Gemini, OpenRouter) estão indisponíveis.\n"
            "Ação recomendada: Verifique as API keys no arquivo .env e tente novamente.\n"
            f"Prompt recebido: {prompt[:100]}..."
        )
    
    async def _publish_usage(self, provider_name: str, task_type: str) -> None:
        """
        Publica uso do provider na MessageBus (se disponível).
        
        Args:
            provider_name: Nome do provider usado
            task_type: Tipo de tarefa executada
        """
        try:
            # Tenta importar MessageBus se disponível
            from core.message_bus import MessageBus
            message_bus = MessageBus()
            
            await message_bus.publish(
                topic="llm.usage",
                data={
                    "provider": provider_name,
                    "task_type": task_type,
                    "timestamp": time.time(),
                    "fallback_chain": [p.name for p in self.providers]
                }
            )
        except Exception as e:
            # MessageBus pode não estar disponível - não é crítico
            self.logger.debug(f"Não foi possível publicar uso na MessageBus: {e}")
    
    def get_usage_stats(self) -> Dict[str, int]:
        """Retorna estatísticas de uso dos providers."""
        return self.usage_stats.copy()


# Legacy LlmAgent para compatibilidade com código existente
class LlmAgent(AgentBase):
    """
    Legacy LLM Agent - wrapper para LLMRouter.
    
    Mantido para compatibilidade com código existente.
    Novo código deve usar LLMRouter diretamente.
    """
    
    def __init__(self, groq_client=None):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "LLM Orchestrator (Groq Powered + Fallback)"
        self.logger = setup_logger("LlmAgent")
        self._config = Config()
        self._router = LLMRouter(self._config)
        self.llm = groq_client  # Mantido para compatibilidade
    
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """Executa tarefa usando LLMRouter com fallback."""
        prompt = kwargs.get("prompt", task)
        model = kwargs.get("model")
        task_type = kwargs.get("task_type", "general")
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        
        # Interceptador de Custo Zero (Diretriz 0.2)
        if model:
            model_lower = model.lower()
            if "gpt" in model_lower or "claude" in model_lower:
                model = "llama-3.3-70b-versatile"
                self.logger.warning(f"Modelo pago {model} bloqueado. Usando fallback gratuito.")
        
        try:
            response = await self._router.complete(
                prompt=prompt,
                task_type=task_type,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return TaskResult(
                success=True,
                data={
                    "response": response,
                    "model_used": "router_with_fallback",
                    "usage_stats": self._router.get_usage_stats()
                }
            )
            
        except Exception as e:
            self.logger.error(f"Erro na execução LLM: {e}")
            return TaskResult(success=False, error=f"Erro LLM: {e}")
    
    async def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file using Groq Whisper (sem fallback)."""
        try:
            from groq import Groq
            api_key = self._config.get("llm.api_key")

            if not api_key or api_key == "COLE_O_SEU_TOKEN_AQUI":
                return "Erro: Groq API Key não configurada no .env"

            client = Groq(api_key=api_key)

            with open(audio_path, "rb") as file:
                transcription = client.audio.transcriptions.create(
                    file=(audio_path, file.read()),
                    model="whisper-large-v3",
                    language="pt"
                )
            return transcription.text

        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")
            return f"Error: {e}"


# ─────────────────────────────────────────────────────────────
#  Utility Functions — Environment Validation
# ─────────────────────────────────────────────────────────────

def validate_llm_env() -> Dict[str, Any]:
    """
    Valida configuração de ambiente para LLM providers.

    Returns:
        Dict com status de cada provider e recomendações.

    Example:
        >>> status = validate_llm_env()
        >>> print(status["groq"]["configured"])
        True
    """
    config = Config()

    groq_key = config.get("llm.api_key") or os.getenv("GROQ_API_KEY")
    gemini_key = config.get("gemini.api_key") or os.getenv("GEMINI_API_KEY")
    openrouter_key = config.get("openrouter.api_key") or os.getenv("OPENROUTER_API_KEY")

    def is_valid_key(key: Optional[str]) -> bool:
        return bool(key and key not in ["", "COLE_O_SEU_TOKEN_AQUI", None])

    groq_valid = is_valid_key(groq_key)
    gemini_valid = is_valid_key(gemini_key)
    openrouter_valid = is_valid_key(openrouter_key)

    providers_configured = []
    providers_available = []

    if groq_valid:
        providers_configured.append("Groq")
        providers_available.append("Groq (llama-3.3-70b, llama-3.1-8b)")

    if gemini_valid:
        providers_configured.append("Gemini")
        providers_available.append("Gemini (gemini-2.0-flash)")

    if openrouter_valid:
        providers_configured.append("OpenRouter")
        providers_available.append("OpenRouter (open-source models)")

    return {
        "configured": {
            "groq": groq_valid,
            "gemini": gemini_valid,
            "openrouter": openrouter_valid,
        },
        "providers_configured": providers_configured,
        "providers_available": providers_available,
        "fallback_chain": providers_configured.copy() if providers_configured else ["degraded_mode"],
        "fully_configured": groq_valid,  # Groq é obrigatório
        "recommendations": _get_env_recommendations(groq_valid, gemini_valid, openrouter_valid),
    }


def _get_env_recommendations(
    groq: bool, gemini: bool, openrouter: bool
) -> List[str]:
    """Gera recomendações baseadas na configuração atual."""
    recommendations = []

    if not groq:
        recommendations.append(
            "⚠️ GROQ_API_KEY não configurada. "
            "Obter em: https://console.groq.com/keys"
        )
    else:
        recommendations.append("✅ Groq configurado (provider primário)")

    if not gemini:
        recommendations.append(
            "ℹ️ GEMINI_API_KEY não configurada (opcional). "
            "Recomendado para fallback. Obter em: https://makersuite.google.com/app/apikey"
        )
    else:
        recommendations.append("✅ Gemini configurado (fallback secundário)")

    if not openrouter:
        recommendations.append(
            "ℹ️ OPENROUTER_API_KEY não configurada (opcional). "
            "Recomendado para fallback terciário. Obter em: https://openrouter.ai/keys"
        )
    else:
        recommendations.append("✅ OpenRouter configurado (fallback terciário)")

    if not groq and not gemini and not openrouter:
        recommendations.append(
            "🚨 Nenhum provider configurado! Sistema operará em MODO DEGRADADO."
        )

    return recommendations


def get_available_llm_providers() -> List[str]:
    """
    Retorna lista de providers de LLM disponíveis (configurados e válidos).

    Returns:
        Lista de nomes de providers na ordem de fallback.

    Example:
        >>> providers = get_available_llm_providers()
        >>> print(providers)
        ['Groq', 'Gemini', 'OpenRouter']
    """
    validation = validate_llm_env()
    return validation["providers_configured"]


def print_llm_status() -> None:
    """
    Imprime status formatado da configuração de LLM.

    Útil para debugging e verificação de ambiente.
    """
    status = validate_llm_env()

    print("\n" + "=" * 60)
    print("  🌕 THE MOON — LLM Provider Status")
    print("=" * 60)
    print()

    print("Providers Configurados:")
    for provider in status["providers_configured"] or ["Nenhum"]:
        print(f"  ✅ {provider}")

    print()
    print("Cadeia de Fallback:")
    for i, provider in enumerate(status["fallback_chain"], 1):
        print(f"  {i}. {provider}")

    print()
    print("Recomendações:")
    for rec in status["recommendations"]:
        print(f"  {rec}")

    print()
    print("=" * 60)
