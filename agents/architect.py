"""
agents/architect.py
The Moon — Orquestrador Central e Decisor Sistêmico

Responsabilidades:
  - Orquestração de agentes: recebe tarefas e delega para o agente adequado
  - Roteamento inteligente via LLM (classificação de domínio)
  - Monitoramento de pipeline: health check de todos os agentes
  - Registro dinâmico de agentes
  - Publicação de decisões e alertas na MessageBus
  - Graceful shutdown com captura de SIGTERM/SIGINT

Domínios suportados:
  - sports: Análise esportiva e apostas
  - economics: Inteligência financeira
  - content: Blog, YouTube, redes sociais
  - devops: Auditoria de código e dependências
  - research: Pesquisa e mineração de dados
  - hardware: Integração com sistema (áudio, voz, GTK)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import time
from typing import Any, Callable, Dict, List, Optional, Set

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus
from utils.logger import setup_logger

logger = setup_logger("ArchitectAgent")

# QwenCodeAgent import
from agents.qwen_code_agent import QwenCodeAgent

# ─────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────
HEALTH_CHECK_INTERVAL = 300  # 5 minutos entre health checks
ALERT_COOLDOWN = 300  # 5 minutos antes do mesmo alerta disparar novamente

# ─────────────────────────────────────────────────────────────
#  Mapeamento de Domínios → Agentes
# ─────────────────────────────────────────────────────────────
DOMAIN_AGENT_MAP = {
    "sports": "SportsAnalyzer",
    "economics": "EconomicSentinel",
    "content": "OmniChannelStrategist",
    "devops": "AutonomousDevOpsRefactor",
    "research": "NexusIntelligence",
    "hardware": "HardwareSynergyBridge",
    "news": "NewsMonitorAgent",
    "crawler": "CrawlerAgent",
    "memory": "SemanticMemoryWeaver",
    "skill": "SkillAlchemist",
    "github": "GithubAgent",
    "watchdog": "WatchdogAgent",
    "opencode": "OpenCodeAgent",
    # Moon-Stack Agents
    "browser": "MoonBrowserAgent",
    "plan": "MoonPlanAgent",
    "review": "MoonReviewAgent",
    "qa": "MoonQAAgent",
    "ship": "MoonShipAgent",
    "cli": "MoonCLIAgent",
    "harness": "MoonCLIAgent",
    "libreoffice": "MoonCLIAgent",
    "mermaid": "MoonCLIAgent",
    # WebMCP Agent
    "web": "WebMCPAgent",
    "search": "WebMCPAgent",
    "fetch": "WebMCPAgent",
    # Text-to-SQL Agent
    "sql": "TextToSQLAgent",
    "database": "TextToSQLAgent",
    "query": "TextToSQLAgent",
    "report": "TextToSQLAgent",
    # Blog Pipeline Agent
    "blog": "BlogPipelineAgent",
    "post": "BlogPipelineAgent",
    "artigo": "BlogPipelineAgent",
    "article": "BlogPipelineAgent",
    "publish": "BlogPipelineAgent",
    # Codex Updater Agent
    "codex": "CodexUpdaterAgent",
    "docs": "CodexUpdaterAgent",
    "documentation": "CodexUpdaterAgent",
    # YouTube Agent
    "youtube": "YouTubeAgent",
    "video": "YouTubeAgent",
    "roteiro": "YouTubeAgent",
    "script": "YouTubeAgent",
    "multimodal": "YouTubeAgent",
    # Hedge Agent
    "hedge": "HedgeAgent",
    "aposta": "HedgeAgent",
    "apostas": "HedgeAgent",
    "kelly": "HedgeAgent",
    "banca": "HedgeAgent",
    "backtest": "HedgeAgent",
    "value_bet": "HedgeAgent",
    # Gmail Agent
    "gmail": "GmailAgent",
    "email": "GmailAgent",
    "inbox": "GmailAgent",
    "triage": "GmailAgent",
    "draft": "GmailAgent",
    # Sports Analytics Agent
    "sports_analytics": "SportsAnalyticsAgent",
    "futebol": "SportsAnalyticsAgent",
    "football": "SportsAnalyticsAgent",
    "soccer": "SportsAnalyticsAgent",
    "standings": "SportsAnalyticsAgent",
    "brasileirao": "SportsAnalyticsAgent",
    "champions": "SportsAnalyticsAgent",
    # QwenCodeAgent
    "code_generation": "QwenCodeAgent",
    "refactoring": "QwenCodeAgent",
    "test_writing": "QwenCodeAgent",
    "harness_generation": "QwenCodeAgent",
}

# Palavras-chave para fallback (regex)
KEYWORD_PATTERNS = {
    "sports": r"(aposta|esporte|futebol|jogo|partida|odd|kelly|apex|bet|time|gol)",
    "economics": r"(economia|mercado|ação|bolsa|investimento|financeiro|banco|crypto|bitcoin|sentinel)",
    "content": r"(blog|post|youtube|vídeo|conteúdo|seo|publicar|thread|tweet|linkedin|canal)",
    "devops": r"(código|teste|lint|segurança|dependência|refator|git|commit|pipeline|ci|cd|build)",
    "research": r"(pesquisa|investigar|analisar|estudar|descobrir|minerar|extrair|relatório|nexus)",
    "hardware": r"(áudio|voz|microfone|gtk|janela|sistema|atalho|teclado|mouse|desktop|ponte)",
    "news": r"(notícia|news|headline|rss|feed|atualidade|última|manchete|g1|bbc|reuters)",
    "crawler": r"(crawl|scrap|rasp|url|site|página|web|html|beautifulsoup|playwright|navegador)",
    "memory": r"(memória|lembrar|conhecimento|grafo|semântico|vetor|embedding|weaver)",
    "skill": r"(habilidade|skill|capacidade|módulo|extensão|plugin|integração|alchemist)",
    "github": r"(github|repositório|commit|pull|issue|branch|merge|clone|repo)",
    "watchdog": r"(saúde|monitor|alerta|cpu|ram|disco|recurso|vigia|guardião|watchdog)",
    "opencode": r"(opencode|local|modelo|llm|inferência|groq|gemini|openrouter|fallback)",
    # Moon-Stack patterns
    "browser": r"(navegar|browser|url|snapshot|screenshot|click|preencher|fill|goto|web|página)",
    "plan": r"(planejar|estratégia|ceo|eng|arquitetura|design|produto|análise|planejamento)",
    "review": r"(review|revisão|código|bug|erro|ast|lint|qualidade|health score)",
    "qa": r"(qa|teste|qualidade|visual|dashboard|interface|frontend|screenshot)",
    "ship": r"(ship|deploy|release|pr|pull request|changelog|push|merge|entrega)",
    # MoonCLIAgent patterns
    "cli": r"(cli|harness|libreoffice|mermaid|diagrama|documento|pdf|exportar|render|cli-anything)",
    # WebMCP Agent patterns
    "web": r"(web|http|https|site|página|url|fetch|buscar|pesquisar|search|scrap)",
    # Text-to-SQL patterns
    "sql": r"(sql|database|query|select|report|relatório|dados|tabela|consulta|banco|postgresql)",
    # Blog Pipeline patterns
    "blog": r"(blog|post|artigo|escrever|escreva|publique|publicar|artigo|conteúdo|redação|texto|postar)",
    # Sports patterns
    "sports_analytics": r"(esporte|futebol|jogo|partida|brasileirao|campeonato|liga|copa|champions|liga dos campeões|liga dos campeões europeus|liga dos campeões da uefa|liga dos campeões da uefa europeus)",
    # Codex Updater patterns
    "codex": r"(codex|moon_codex|atualizar.*documento|documentação|log|histórico|sprint|feat)",
    # YouTube patterns
    "youtube": r"(youtube|vídeo|roteiro|script|thumbnail|seo.*youtube|trending|vídeo.*youtube)",
    # Hedge patterns
    "hedge": r"(hedge|aposta|apostas|kelly|banca|backtest|value.*bet|odd|probabilidade.*aposta)",
    # Gmail patterns
    "gmail": r"(gmail|email|inbox|triage|draft|responder.*email|ler.*email|mensagem.*gmail)",
    # QwenCodeAgent patterns
    "code_generation": r"(gerar.*código|criar.*código|gerar.*função|criar.*classe|implementar|scaffold|boilerplate|code generation)",
    "refactoring": r"(refatorar|refatoração|refactor|limpar.*código|otimizar.*código|melhorar.*código)",
    "test_writing": r"(criar.*teste|escrever.*teste|gerar.*teste|testes unitários|mock|pytest|unittest)",
    "harness_generation": r"(harness|cli-anything|wrapper|cli.*tool|ferramenta.*cli)",
}


class ArchitectAgent(AgentBase):
    """
    Orquestrador central do ecossistema The Moon.
    
    Responsabilidades:
      - Receber tarefas e classificar o domínio
      - Delegar para o agente apropriado
      - Monitorar saúde de todos os agentes registrados
      - Publicar decisões e alertas na MessageBus
      - Suportar registro dinâmico de novos agentes
    """

    def __init__(self, message_bus: Optional[MessageBus] = None) -> None:
        super().__init__()
        self.name = "ArchitectAgent"
        self.description = "Orquestrador central: classifica, roteia e monitora tarefas."
        self.priority = AgentPriority.CRITICAL

        # MessageBus
        self._message_bus = message_bus or MessageBus()

        # Agentes registrados: Dict[name, Dict[metadata]]
        self._registered_agents: Dict[str, Dict[str, Any]] = {}

        # Agentes críticos (devem estar sempre disponíveis)
        self._critical_agents: Set[str] = {
            "WatchdogAgent",
            "EconomicSentinel",
            "NexusIntelligence",
        }

        # Health check em background
        self._stop_event = asyncio.Event()
        self._health_check_task: Optional[asyncio.Task] = None

        # Alert deduplication
        self._alert_last_seen: Dict[str, float] = {}

        # LLM Router (import lazy para evitar circular dependency)
        self._llm_router = None

        # Status cache (atualizado a cada health check)
        self._agent_status_cache: Dict[str, Dict[str, Any]] = {}

        # Callbacks de agentes (injetados manualmente ou via auto-discovery)
        self._agent_instances: Dict[str, Any] = {}

        # Skill Registry (adicionado após DOMAIN_AGENT_MAP)
        from core.skill_manifest import get_skill_registry
        self.skill_registry = get_skill_registry()
        self.skill_registry.discover("skills")

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        """Inicializa o Architect e registra agentes conhecidos."""
        await super().initialize()

        # Registrar na MessageBus
        self._message_bus.subscribe(
            "architect.command",
            self._handle_incoming_command
        )

        # Iniciar health check em background
        self._stop_event.clear()
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(),
            name="moon.architect.health_check"
        )

        # Registrar agentes hardcoded (conforme MOON_CODEX Seção 5)
        await self._register_known_agents()

        logger.info("ArchitectAgent initialized — pronto para orquestrar.")

    async def shutdown(self) -> None:
        """Encerramento limpo: para loops e libera recursos."""
        self._stop_event.set()

        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Cancelar todas as tarefas pendentes dos agentes
        for agent_name, agent_instance in self._agent_instances.items():
            try:
                if hasattr(agent_instance, 'shutdown'):
                    await agent_instance.shutdown()
            except Exception as e:
                logger.error(f"Erro ao shutdown do agente {agent_name}: {e}")

        await super().shutdown()
        logger.info("ArchitectAgent shut down — encerramento limpo.")

    # ═══════════════════════════════════════════════════════════
    #  Execute Dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, task: str, **kwargs: Any) -> TaskResult:
        """
        Ações suportadas:
          orchestrate: Orquestra uma tarefa (auto-classifica e delega)
          classify: Apenas classifica o domínio (sem delegar)
          status: Retorna status de todos os agentes
          register: Registra um novo agente dinamicamente
          health: Health check imediato
        """
        action = kwargs.get("action", "orchestrate")

        match action:
            case "orchestrate":
                return await self.orchestrate_task(task, **kwargs)

            case "classify":
                domain = await self._classify_domain(task)
                return TaskResult(
                    success=True,
                    data={"domain": domain, "task": task}
                )

            case "status":
                return TaskResult(
                    success=True,
                    data={"agents": self.get_pipeline_status()}
                )

            case "register":
                agent_name = kwargs.get("name")
                module_path = kwargs.get("module_path")
                topics = kwargs.get("topics", [])
                await self.register_agent(agent_name, module_path, topics)
                return TaskResult(
                    success=True,
                    data={"registered": agent_name}
                )

            case "health":
                status = await self._check_all_agents_health()
                return TaskResult(
                    success=all(s.get("healthy", True) for s in status.values()),
                    data={"health": status}
                )

            case _:
                return TaskResult(
                    success=False,
                    error=f"Ação desconhecida: '{action}'"
                )

    # ═══════════════════════════════════════════════════════════
    #  Orquestração Principal
    # ═══════════════════════════════════════════════════════════

    async def orchestrate_task(
        self,
        task: str,
        **kwargs: Any
    ) -> TaskResult:
        """
        Recebe uma tarefa, classifica o domínio e delega para o agente adequado.
        
        Fluxo:
          1. Classifica o domínio da tarefa (LLM ou fallback regex)
          2. Identifica o agente alvo
          3. Verifica saúde do agente (Watchdog.ping())
          4. Delega a tarefa
          5. Publica decisão na MessageBus
        """
        start_time = time.time()
        logger.info(f"Orquestrando tarefa: {task[:100]}...")

        try:
            # Passo 1: Classificar domínio
            domain = await self._classify_domain(task)
            logger.info(f"Domínio classificado: {domain}")

            # Passo 2: Identificar agente alvo
            target_agent = DOMAIN_AGENT_MAP.get(domain)
            if not target_agent:
                logger.warning(f"Domínio '{domain}' sem agente mapeado. Usando fallback.")
                target_agent = "NexusIntelligence"  # Fallback padrão

            # Passo 3: Verificar saúde do agente (se Watchdog disponível)
            agent_healthy = await self._verify_agent_health(target_agent)
            if not agent_healthy:
                error_msg = f"Agente {target_agent} indisponível"
                logger.error(error_msg)
                self._fire_alert("agent_unavailable", error_msg)
                return TaskResult(success=False, error=error_msg)

            # Passo 4: Delegar tarefa
            result = await self._delegate_task(
                agent_name=target_agent,
                task=task,
                **kwargs
            )

            # Passo 5: Publicar decisão na MessageBus
            execution_time = time.time() - start_time
            await self._publish_decision(
                domain=domain,
                target_agent=target_agent,
                task=task,
                success=result.success,
                execution_time=execution_time
            )

            return result

        except Exception as e:
            logger.error(f"Erro na orquestração: {e}")
            return TaskResult(success=False, error=str(e))

    # ═══════════════════════════════════════════════════════════
    #  Classificação de Domínio (LLM + Fallback)
    # ═══════════════════════════════════════════════════════════

    async def _classify_domain(self, task: str) -> str:
        """
        Classifica o domínio de uma tarefa usando:
          1. LLM (llama-3.1-8b) para classificação semântica
          2. Fallback: regex por palavras-chave
        """
        # Tenta LLM primeiro
        try:
            llm_result = await self._call_llm_classifier(task)
            if llm_result:
                return llm_result
        except Exception as e:
            logger.warning(f"LLM de classificação falhou: {e}. Usando fallback regex.")

        # Fallback: regex por palavras-chave
        return self._classify_by_keywords(task)

    async def _call_llm_classifier(self, task: str) -> Optional[str]:
        """
        Usa LLM (llama-3.1-8b) para classificar o domínio.
        
        Prompt estruturado para resposta determinística.
        """
        try:
            from agents.llm import LLMRouter
            
            if self._llm_router is None:
                self._llm_router = LLMRouter()
            
            prompt = (
                f"Classifique a tarefa abaixo em UM destes domínios: "
                f"{', '.join(DOMAIN_AGENT_MAP.keys())}\n\n"
                f"Tarefa: {task}\n\n"
                f"Responda APENAS com o nome do domínio (uma palavra)."
            )
            
            response = await self._llm_router.complete(
                prompt=prompt,
                task_type="fast",
                model="llama-3.1-8b-instant"
            )
            
            # Extrai domínio da resposta
            domain = response.strip().lower()
            
            # Valida se é um domínio conhecido
            if domain in DOMAIN_AGENT_MAP:
                return domain
            
            # Tenta encontrar substring match
            for known_domain in DOMAIN_AGENT_MAP.keys():
                if known_domain in domain:
                    return known_domain
            
            return None
            
        except ImportError:
            logger.warning("LLMRouter não disponível. Usando fallback.")
            return None
        except Exception as e:
            logger.error(f"Erro na classificação LLM: {e}")
            return None

    def _classify_by_keywords(self, task: str) -> str:
        """
        Fallback: classifica por palavras-chave (regex).
        """
        task_lower = task.lower()
        
        for domain, pattern in KEYWORD_PATTERNS.items():
            if re.search(pattern, task_lower):
                logger.debug(f"Match por keyword: domínio={domain}")
                return domain
        
        # Default fallback
        logger.debug("Nenhum match encontrado. Usando domínio 'research' como default.")
        return "research"

    # ═══════════════════════════════════════════════════════════
    #  Delegação de Tarefas
    # ═══════════════════════════════════════════════════════════

    async def _delegate_task(
        self,
        agent_name: str,
        task: str,
        **kwargs: Any
    ) -> TaskResult:
        """
        Delega uma tarefa para um agente específico.
        
        Estratégias:
          1. Se agente injetado (_agent_instances): chama execute() diretamente
          2. Se MessageBus disponível: publica no tópico do agente
          3. Fallback: tenta import dinâmico
        """
        logger.info(f"Delegando para {agent_name}: {task[:50]}...")

        # Estratégia 1: Agente injetado
        if agent_name in self._agent_instances:
            agent = self._agent_instances[agent_name]
            if hasattr(agent, 'execute'):
                return await agent.execute(task, **kwargs)
            elif hasattr(agent, '_execute'):
                return await agent._execute(task, **kwargs)

        # Estratégia 2: Publica na MessageBus
        agent_topic = f"{agent_name.lower()}.command"
        try:
            await self._message_bus.publish(
                sender=self.name,
                topic=agent_topic,
                payload={"task": task, "kwargs": kwargs},
                target=agent_name.lower()
            )
            logger.info(f"Tarefa publicada no tópico {agent_topic}")
            
            # Retorna sucesso imediato (agente processará assincronamente)
            return TaskResult(
                success=True,
                data={
                    "delegated": True,
                    "agent": agent_name,
                    "topic": agent_topic,
                    "message": "Tarefa publicada na MessageBus para processamento assíncrono"
                }
            )
        except Exception as e:
            logger.error(f"Erro ao publicar na MessageBus: {e}")

        # Estratégia 3: Import dinâmico (fallback)
        try:
            agent_module = await self._import_agent_module(agent_name)
            if agent_module:
                agent_class = getattr(agent_module, agent_name)
                agent = agent_class()
                await agent.initialize()
                self._agent_instances[agent_name] = agent
                return await agent.execute(task, **kwargs)
        except Exception as e:
            logger.error(f"Erro ao importar agente {agent_name}: {e}")

        # Falha total
        return TaskResult(
            success=False,
            error=f"Não foi possível delegar para {agent_name}"
        )

    async def _import_agent_module(self, agent_name: str) -> Optional[Any]:
        """
        Importa dinamicamente o módulo de um agente.
        """
        try:
            # Mapeamento de nomes para módulos
            module_map = {
                "SportsAnalyzer": "agents.sports.analyzer",
                "EconomicSentinel": "agents.economic_sentinel",
                "OmniChannelStrategist": "agents.omni_channel_strategist",
                "AutonomousDevOpsRefactor": "agents.autonomous_devops_refactor",
                "NexusIntelligence": "agents.nexus_intelligence",
                "HardwareSynergyBridge": "agents.hardware_synergy_bridge",
                "NewsMonitorAgent": "agents.news_monitor",
                "CrawlerAgent": "agents.crawler",
                "SemanticMemoryWeaver": "agents.semantic_memory_weaver",
                "SkillAlchemist": "agents.skill_alchemist",
                "GithubAgent": "agents.github_agent",
                "WatchdogAgent": "agents.watchdog",
                "OpenCodeAgent": "agents.opencode",
            }
            
            module_path = module_map.get(agent_name)
            if not module_path:
                # Tenta padrão: agents.{agent_name_snake_case}
                module_path = f"agents.{self._to_snake_case(agent_name)}"
            
            import importlib
            module = importlib.import_module(module_path)
            return module
            
        except ImportError as e:
            logger.debug(f"Import dinâmico falhou para {agent_name}: {e}")
            return None

    # ═══════════════════════════════════════════════════════════
    #  Health Check e Monitoramento
    # ═══════════════════════════════════════════════════════════

    async def _check_all_agents_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Verifica saúde de todos os agentes registrados.
        """
        status = {}
        
        for agent_name in self._registered_agents.keys():
            try:
                # Tenta ping() se o agente estiver injetado
                if agent_name in self._agent_instances:
                    agent = self._agent_instances[agent_name]
                    if hasattr(agent, 'ping'):
                        is_healthy = await agent.ping()
                    elif hasattr(agent, 'is_initialized'):
                        is_healthy = agent.is_initialized
                    else:
                        is_healthy = True
                else:
                    # Agente não injetado: assume saudável se estiver registrado
                    is_healthy = True
                
                status[agent_name] = {
                    "healthy": is_healthy,
                    "registered": True,
                    "critical": agent_name in self._critical_agents
                }
                
            except Exception as e:
                status[agent_name] = {
                    "healthy": False,
                    "error": str(e),
                    "critical": agent_name in self._critical_agents
                }
        
        return status

    async def _verify_agent_health(self, agent_name: str) -> bool:
        """
        Verifica se um agente específico está saudável.
        """
        if agent_name in self._agent_instances:
            agent = self._agent_instances[agent_name]
            if hasattr(agent, 'ping'):
                return await agent.ping()
            elif hasattr(agent, 'is_initialized'):
                return agent.is_initialized
        
        # Se não está injetado, assume saudável (será verificado no health check)
        return True

    async def _health_check_loop(self) -> None:
        """
        Loop de health check em background (a cada 5 minutos).
        """
        logger.info("Health check loop iniciado.")
        
        while not self._stop_event.is_set():
            try:
                status = await self._check_all_agents_health()
                self._agent_status_cache = status
                
                # Verifica agentes críticos
                for agent_name, agent_status in status.items():
                    if agent_status.get("critical") and not agent_status.get("healthy"):
                        self._fire_alert(
                            "critical_agent_down",
                            f"Agente crítico {agent_name} está DOWN"
                        )
                        logger.error(f"ALERTA: Agente crítico {agent_name} indisponível!")
                
                # Publica status na MessageBus
                await self._publish_health_status(status)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no health check: {e}")
            
            # Aguarda próximo ciclo
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=HEALTH_CHECK_INTERVAL
                )
                break  # stop_event foi setado
            except asyncio.TimeoutError:
                pass  # Continua loop
        
        logger.info("Health check loop encerrado.")

    # ═══════════════════════════════════════════════════════════
    #  Registro de Agentes
    # ═══════════════════════════════════════════════════════════

    async def register_agent(
        self,
        name: str,
        module_path: str,
        topics: List[str] = None
    ) -> None:
        """
        Registra um agente dinamicamente.
        
        Args:
            name: Nome do agente
            module_path: Caminho do módulo (ex: "agents.my_agent")
            topics: Tópicos que o agente consome (opcional)
        """
        self._registered_agents[name] = {
            "module_path": module_path,
            "topics": topics or [],
            "registered_at": time.time()
        }
        
        logger.info(f"Agente {name} registrado (módulo: {module_path})")
        
        # Tenta importar e injetar instância
        try:
            import importlib
            module = importlib.import_module(module_path)
            agent_class = getattr(module, name)
            agent = agent_class()
            await agent.initialize()
            self._agent_instances[name] = agent
            logger.info(f"Instância de {name} injetada com sucesso")
        except Exception as e:
            logger.warning(f"Não foi possível injetar instância de {name}: {e}")

    async def _register_known_agents(self) -> None:
        """
        Registra agentes conhecidos (hardcoded conforme MOON_CODEX).
        """
        known_agents = {
            "WatchdogAgent": ("agents.watchdog", ["watchdog.command"]),
            "EconomicSentinel": ("agents.economic_sentinel", ["economics.command"]),
            "NexusIntelligence": ("agents.nexus_intelligence", ["nexus.command"]),
            "OmniChannelStrategist": ("agents.omni_channel_strategist", ["omni.command"]),
            "AutonomousDevOpsRefactor": ("agents.autonomous_devops_refactor", ["devops.command"]),
            "SemanticMemoryWeaver": ("agents.semantic_memory_weaver", ["memory.command"]),
            "SkillAlchemist": ("agents.skill_alchemist", ["skill.command"]),
            "GithubAgent": ("agents.github_agent", ["github.command"]),
            "OpenCodeAgent": ("agents.opencode", ["opencode.command"]),
            # Moon-Stack Agents
            "MoonBrowserAgent": ("agents.moon_browser_agent", ["browser.command"]),
            "MoonPlanAgent": ("agents.moon_plan_agent", ["plan.command"]),
            "MoonReviewAgent": ("agents.moon_review_agent", ["review.command"]),
            "MoonQAAgent": ("agents.moon_qa_agent", ["qa.command"]),
            "MoonShipAgent": ("agents.moon_ship_agent", ["ship.command"]),
            # MoonCLIAgent
            "MoonCLIAgent": ("agents.moon_cli_agent", ["cli.command", "cli.execute", "cli.generate", "cli.discover"]),
            # WebMCP Agent
            "WebMCPAgent": ("agents.webmcp_agent", ["web.command", "search.command", "fetch.command"]),
            # Text-to-SQL Agent
            "TextToSQLAgent": ("agents.text_to_sql_agent", ["sql.command", "query.command", "db.command"]),
            # Codex Updater Agent
            "CodexUpdaterAgent": ("agents.codex_updater", ["codex.update", "codex.command"]),
            # YouTube Agent
            "YouTubeAgent": ("agents.youtube_agent", ["youtube.command", "video.command", "script.command"]),
            # Hedge Agent
            "HedgeAgent": ("agents.hedge_agent", ["hedge.command", "bet.command", "kelly.command"]),
            # Gmail Agent
            "GmailAgent": ("agents.gmail_agent", ["gmail.command", "email.command", "triage.command"]),
        }

        for name, (module_path, topics) in known_agents.items():
            await self.register_agent(name, module_path, topics)

        logger.info(f"{len(known_agents)} agentes conhecidos registrados.")

    # ═══════════════════════════════════════════════════════════
    #  MessageBus Publishing
    # ═══════════════════════════════════════════════════════════

    async def _publish_decision(
        self,
        domain: str,
        target_agent: str,
        task: str,
        success: bool,
        execution_time: float
    ) -> None:
        """Publica decisão de orquestração na MessageBus."""
        try:
            await self._message_bus.publish(
                sender=self.name,
                topic="architect.decision",
                payload={
                    "domain": domain,
                    "target_agent": target_agent,
                    "task": task[:200],  # Trunca para não poluir
                    "success": success,
                    "execution_time": execution_time,
                    "timestamp": time.time()
                }
            )
        except Exception as e:
            logger.debug(f"Não foi possível publicar decisão: {e}")

    async def _publish_health_status(self, status: Dict[str, Dict]) -> None:
        """Publica status de saúde na MessageBus."""
        try:
            await self._message_bus.publish(
                sender=self.name,
                topic="architect.health",
                payload={
                    "status": status,
                    "timestamp": time.time(),
                    "critical_agents": list(self._critical_agents)
                }
            )
        except Exception as e:
            logger.debug(f"Não foi possível publicar health status: {e}")

    async def _handle_incoming_command(self, message: Any) -> None:
        """
        Handler para comandos recebidos na MessageBus.
        """
        try:
            payload = message.payload if hasattr(message, 'payload') else message
            
            if isinstance(payload, dict):
                task = payload.get("task", "")
                kwargs = payload.get("kwargs", {})
                
                if task:
                    await self.orchestrate_task(task, **kwargs)
        except Exception as e:
            logger.error(f"Erro ao processar comando: {e}")

    # ═══════════════════════════════════════════════════════════
    #  Alert System
    # ═══════════════════════════════════════════════════════════

    def _fire_alert(self, alert_key: str, message: str) -> None:
        """
        Dispara alerta com deduplicação (cooldown de 5 minutos).
        """
        now = time.monotonic()
        last = self._alert_last_seen.get(alert_key, 0.0)
        
        if now - last < ALERT_COOLDOWN:
            return  # Still in cooldown
        
        self._alert_last_seen[alert_key] = now
        
        # Publica na MessageBus
        asyncio.create_task(
            self._message_bus.publish(
                sender=self.name,
                topic="architect.alert",
                payload={"key": alert_key, "message": message, "timestamp": time.time()}
            )
        )
        
        logger.warning(f"ALERTA Architect: {message}")

    # ═══════════════════════════════════════════════════════════
    #  Public API
    # ═══════════════════════════════════════════════════════════

    def get_pipeline_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Retorna status atual de todos os agentes conhecidos.
        """
        return self._agent_status_cache.copy()

    def get_skills_for_domain(self, domain: str) -> list:
        return [s.name for s in self.skill_registry.list_by_domain(domain)]
        
    # ═══════════════════════════════════════════════════════════
    #  Utilities
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Converte CamelCase para snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


# ═══════════════════════════════════════════════════════════════
#  Graceful Shutdown Handler (SIGTERM/SIGINT)
# ═══════════════════════════════════════════════════════════════

def setup_graceful_shutdown(architect: ArchitectAgent) -> None:
    """
    Configura handler para SIGTERM/SIGINT para encerramento limpo.
    """
    loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(
                _graceful_shutdown(architect),
                name="moon.architect.graceful_shutdown"
            )
        )


async def _graceful_shutdown(architect: ArchitectAgent) -> None:
    """
    Executa shutdown limpo do Architect.
    """
    logger.info("Recebido sinal de término. Iniciando shutdown limpo...")
    await architect.shutdown()
    logger.info("Shutdown limpo concluído.")
