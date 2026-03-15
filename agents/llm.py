"""
agents/llm.py
LLM Orchestrator.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from core.config import Config
from utils.logger import setup_logger
from groq import AsyncGroq
import os

class LlmAgent(AgentBase):
    def __init__(self, groq_client=None):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "LLM Orchestrator (Groq Powered)"
        self.logger = setup_logger("LlmAgent")
        self._config = Config()
        self.llm = groq_client

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        prompt = kwargs.get("prompt", task)
        image_base64 = kwargs.get("image_base64")
        
        # Load constraints
        api_key = self._config.get("llm.api_key")
        model = kwargs.get("model") or self._config.get("llm.model", "llama-3.3-70b-versatile")
        
        # INTERCEPTADOR DE CUSTO ZERO (DIRETRIZ 0.2)
        # Previne o erro "The model `gpt-4` does not exist" na Groq e aplica a ordem de uso exclusivo de Free-Tiers.
        model_lower = model.lower()
        if "gpt" in model_lower or "claude" in model_lower or "gemini" in model_lower:
            model = "llama-3.3-70b-versatile"
            
        temperature = kwargs.get("temperature") or self._config.get("llm.temperature", 0.7)
        max_tokens = kwargs.get("max_tokens") or self._config.get("llm.max_tokens", 4096)
        
        if image_base64:
             model = "llama-3.2-11b-vision-preview"
             messages = [
                 {
                     "role": "user",
                     "content": [
                         {"type": "text", "text": prompt},
                         {
                             "type": "image_url",
                             "image_url": {
                                 "url": f"data:image/jpeg;base64,{image_base64}",
                             },
                         },
                     ],
                 }
             ]
        else:
             messages = [
                 {
                     "role": "user",
                     "content": prompt
                 }
             ]
        
        if not api_key or api_key == "COLE_O_SEU_TOKEN_AQUI":
             return TaskResult(success=False, error="Groq API Key não configurada no .env")
             
        if image_base64:
             model = "llama-3.2-11b-vision-preview"
             models_pool = [model] # Limit output pool for vision tasks to avoid non-vision model errors
        else:
             # POOL DE MODELOS PARA RODÍZIO (DIRETRIZ DE RESILIÊNCIA)
             models_pool = [model, "llama-3.1-8b-instant", "gemma2-9b-it"]
        
        # Remove duplicates while keeping order
        models_pool = list(dict.fromkeys(models_pool))
        
        last_error = ""
        for current_model in models_pool:
            try:
                self.logger.info(f"Tentando execução LLM com modelo: {current_model}")
                client = self.llm or AsyncGroq(api_key=api_key)
                completion = await client.chat.completions.create(
                    messages=messages,
                    model=current_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                response_text = completion.choices[0].message.content
                return TaskResult(success=True, data={"response": response_text, "model_used": current_model})
            except Exception as e:
                err_msg = str(e)
                last_error = err_msg
                # Se for erro de limite (Rate Limit) ou indisponibilidade, tenta o próximo
                if "429" in err_msg or "rate_limit" in err_msg.lower() or "overloaded" in err_msg.lower():
                    self.logger.warning(f"Limite atingido ou erro detectado no modelo {current_model}. Rotacionando...")
                    continue
                else:
                    # Se for outro erro fatal, interrompe
                    return TaskResult(success=False, error=f"Erro fatal na API Groq: {err_msg}")
                    
        return TaskResult(success=False, error=f"Todos os modelos do pool falharam ou atingiram o limite. Último erro: {last_error}")

    async def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file using Groq Whisper."""
        try:
            from groq import Groq
            api_key = self._config.get("llm.api_key")
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

