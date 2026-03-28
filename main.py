"""
main.py
The Moon System Entry Point — Architect-Centric Bootstrap

MOON_CODEX Directive 0.3:
  - ArchitectAgent é o coordenador central do startup
  - Graceful degradation: falhas em sub-agentes não críticos não matam o sistema
  - Logging e observabilidade desde o bootstrap
  - Shutdown limpo com SIGINT/SIGTERM

Fluxo de Inicialização:
  1. Setup de logging e configuração
  2. Inicialização do Orchestrator (infraestrutura base)
  3. Registro de agentes core (Watchdog, LLM, Terminal, FileManager)
  4. Instanciação e inicialização do ArchitectAgent
  5. ArchitectAgent registra e gerencia sub-agentes
  6. Inicialização de canais
  7. Start de loops de background
  8. Handler de shutdown limpo
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import Dict, List, Optional

from core.config import Config
from core.orchestrator import Orchestrator
from core.message_bus import MessageBus
from core.agent_base import AgentPriority
from core.hive_integration import HiveIntegration

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Logger principal
logger = logging.getLogger("moon.main")


# ─────────────────────────────────────────────────────────────
#  Bootstrap Functions
# ─────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """Configura logging para todo o ecossistema."""
    log_format = "%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s"
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("moon_system.log", encoding="utf-8"),
        ],
    )
    
    # Loggers específicos
    logging.getLogger("moon.core").setLevel(logging.DEBUG)
    logging.getLogger("moon.agents").setLevel(logging.DEBUG)
    logging.getLogger("moon.channels").setLevel(logging.INFO)


def validate_environment() -> Dict[str, bool]:
    """
    Valida variáveis de ambiente críticas.
    
    Returns:
        Dict com status de cada variável crítica.
    """
    from agents.llm import validate_llm_env
    
    llm_status = validate_llm_env()
    
    status = {
        "llm_configured": llm_status["fully_configured"],
        "groq_available": llm_status["configured"]["groq"],
        "gemini_available": llm_status["configured"]["gemini"],
        "openrouter_available": llm_status["configured"]["openrouter"],
    }
    
    # Log status
    if status["llm_configured"]:
        logger.info(f"✅ LLM providers disponíveis: {llm_status['providers_configured']}")
    else:
        logger.warning("⚠️ Nenhum LLM provider configurado. Sistema operará em modo degradado.")
    
    return status


async def bootstrap_system(config_path: Optional[str] = None) -> "MoonSystem":
    """
    Inicializa o sistema The Moon com ArchitectAgent como coordenador.
    
    Fluxo:
      1. Configura logging
      2. Valida ambiente
      3. Cria instância do MoonSystem
      4. Inicializa componentes base
      5. Registra agentes via ArchitectAgent
    
    Args:
        config_path: Caminho opcional para arquivo de configuração
    
    Returns:
        Instância do MoonSystem inicializada
    """
    logger.info("🌕 Inicializando The Moon Ecosystem...")
    
    # Setup logging
    setup_logging()
    
    # Valida ambiente
    env_status = validate_environment()
    
    # Cria sistema
    system = MoonSystem(config_path=config_path)
    
    # Bootstrap do Orchestrator (infraestrutura base)
    await system._bootstrap_orchestrator()
    
    # Bootstrap de agentes core
    await system._bootstrap_core_agents()
    
    # Bootstrap do ArchitectAgent (coordenador central)
    await system._bootstrap_architect()
    
    # Bootstrap de agentes especializados (via Architect)
    await system._bootstrap_specialized_agents()
    
    # Bootstrap de canais
    await system._bootstrap_channels()
    
    logger.info("✅ The Moon Ecosystem inicializado com sucesso.")
    
    return system


# ─────────────────────────────────────────────────────────────
#  MoonSystem Class
# ─────────────────────────────────────────────────────────────

class MoonSystem:
    """
    Sistema The Moon — Middleware Cognitivo Universal.
    
    Atributos:
        orchestrator: Orchestrator central
        architect: ArchitectAgent (coordenador principal)
        config: Configurações do sistema
        message_bus: Barramento de mensagens
    """
    
    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Inicializa MoonSystem.
        
        Args:
            config_path: Caminho opcional para arquivo de configuração
        """
        self.config = Config()
        
        if config_path:
            os.environ["MOON_CONFIG_PATH"] = config_path
        
        self.orchestrator = Orchestrator()
        self.architect: Optional["ArchitectAgent"] = None
        self.message_bus = self.orchestrator.message_bus
        self.hive_integration: HiveIntegration | None = None

        # FastAPI Dashboard Support
        self._api_server = None
        self._api_server_task = None

        # Estado do sistema
        self._initialized = False
        self._shutdown_event = asyncio.Event()
    
    async def _bootstrap_orchestrator(self) -> None:
        """Inicializa infraestrutura base do Orchestrator."""
        logger.info("Inicializando Orchestrator...")
        
        # Workspace manager
        await self.orchestrator.workspace_manager.create_room(
            "orchestrator", "Core System"
        )
        
        logger.info("✅ Orchestrator infraestrutura pronta.")
    
    async def _bootstrap_core_agents(self) -> None:
        """Registra agentes core (críticos para operação)."""
        logger.info("Registrando agentes core...")
        
        from agents.watchdog import WatchdogAgent
        from agents.llm import LlmAgent
        from agents.terminal import TerminalAgent
        from agents.file_manager import FileManagerAgent
        
        # Watchdog (monitoramento de saúde)
        watchdog = WatchdogAgent(message_bus=self.message_bus)
        self.orchestrator.register_agent(watchdog)
        
        # LLM (inteligência)
        llm_agent = LlmAgent(groq_client=self.orchestrator.llm)
        self.orchestrator.register_agent(llm_agent)
        
        # Terminal (automação)
        terminal_agent = TerminalAgent()
        self.orchestrator.register_agent(terminal_agent)
        
        # FileManager (gestão de arquivos)
        file_manager = FileManagerAgent()
        self.orchestrator.register_agent(file_manager)
        
        logger.info("✅ Agentes core registrados: Watchdog, LLM, Terminal, FileManager")
    
    async def _bootstrap_architect(self) -> None:
        """
        Inicializa ArchitectAgent como coordenador central.
        
        Este é o ponto de entrada operacional prometido no projeto.
        O ArchitectAgent assume a orquestração de todos os sub-agentes.
        """
        logger.info("Inicializando ArchitectAgent (coordenador central)...")
        
        from agents.architect import ArchitectAgent
        
        # Cria e registra ArchitectAgent
        self.architect = ArchitectAgent(message_bus=self.message_bus)
        self.orchestrator.register_agent(self.architect)
        
        # Injeta instância do Architect no Orchestrator para coordenação
        self.orchestrator._agents["ArchitectAgent"] = self.architect
        
        # Inicializa Architect
        await self.architect.initialize()
        
        logger.info("✅ ArchitectAgent inicializado — orquestração central ativa.")
    
    async def _bootstrap_specialized_agents(self) -> None:
        """
        Registra agentes especializados via ArchitectAgent.
        
        Graceful degradation: falhas em agentes não críticos não matam o sistema.
        """
        logger.info("Registrando agentes especializados...")
        
        agents_registered = 0
        agents_failed = 0
        
        # Lista de agentes especializados (import lazy para evitar circular dependency)
        specialized_agents = self._get_specialized_agents_list()
        
        for agent_name, agent_factory in specialized_agents:
            try:
                agent = agent_factory()
                self.orchestrator.register_agent(agent)
                
                # Registra no Architect para orquestração
                if self.architect:
                    await self._register_with_architect(agent_name, agent)
                
                agents_registered += 1
                logger.debug(f"  ✅ {agent_name}")
                
            except Exception as e:
                agents_failed += 1
                logger.error(f"  ❌ {agent_name}: {e}")
                # Graceful degradation: continua registrando outros agentes
        
        logger.info(
            f"✅ Agentes especializados: {agents_registered} registrados, "
            f"{agents_failed} falharam (graceful degradation)"
        )
    
    def _get_specialized_agents_list(self) -> List[tuple[str, callable]]:
        """
        Retorna lista de fábricas de agentes especializados.
        
        Returns:
            Lista de tuplas (nome, factory_function)
        """
        from groq import AsyncGroq
        
        groq_client = self.orchestrator.llm
        
        return [
            # ── Autonomy & Proactivity (first, so they start watching immediately) ──
            ("MoonSentinelAgent", lambda: self._safe_import_agent(
                "agents.moon_sentinel",
                "MoonSentinelAgent",
                orchestrator=self.orchestrator
            )),
            ("AutonomyEvolutionAgent", lambda: self._safe_import_agent(
                "agents.autonomy_evolution_agent",
                "AutonomyEvolutionAgent",
                orchestrator=self.orchestrator
            )),
            
            # Infra / Base
            ("ProactiveAgent", lambda: self._safe_import_agent("agents.proactive", "ProactiveAgent")),
            ("NewsMonitorAgent", lambda: self._safe_import_agent("agents.news_monitor", "NewsMonitorAgent")),
            ("VaultAgent", lambda: self._safe_import_agent("agents.vault", "VaultAgent")),
            ("ApiDiscoveryAgent", lambda: self._safe_import_agent("agents.api_discovery", "ApiDiscoveryAgent")),
            ("DesktopAgent", lambda: self._safe_import_agent("agents.desktop", "DesktopAgent")),
            ("ContextAgent", lambda: self._safe_import_agent("agents.context", "ContextAgent")),
            ("CrawlerAgent", lambda: self._safe_import_agent("agents.crawler", "CrawlerAgent")),
            ("ResearcherAgent", lambda: self._safe_import_agent("agents.researcher", "ResearcherAgent")),
            ("WebMCPAgent", lambda: self._safe_import_agent("agents.webmcp_agent", "WebMCPAgent")),
            ("MoonPlanAgent", lambda: self._safe_import_agent("agents.moon_plan_agent", "MoonPlanAgent")),
            ("MoonReviewAgent", lambda: self._safe_import_agent("agents.moon_review_agent", "MoonReviewAgent")),
            ("MoonBrowserAgent", lambda: self._safe_import_agent("agents.moon_browser_agent", "MoonBrowserAgent")),

            
            # Content / Writing
            ("BlogManagerAgent", lambda: self._safe_import_agent("agents.blog", "BlogManagerAgent")),
            ("BlogWriterAgent", lambda: self._safe_import_agent("agents.blog", "BlogWriterAgent")),
            ("BlogPublisherAgent", lambda: self._safe_import_agent("agents.blog", "BlogPublisherAgent")),
            ("PromptEnhancerAgent", lambda: self._safe_import_agent("agents.prompt_enhancer", "PromptEnhancerAgent")),
            ("DirectWriterAgent", lambda: self._safe_import_agent("agents.blog", "DirectWriterAgent")),
            ("YoutubeManagerAgent", lambda: self._safe_import_agent("agents.youtube_manager", "YoutubeManagerAgent")),
            ("YouTubeAgent", lambda: self._safe_import_agent("agents.youtube_agent", "YouTubeAgent")),
            ("EmailAgent", lambda: self._safe_import_agent("agents.email_agent", "EmailAgent")),
            ("GmailAgent", lambda: self._safe_import_agent("agents.gmail_agent", "GmailAgent")),
            ("HedgeAgent", lambda: self._safe_import_agent("agents.hedge_agent", "HedgeAgent")),
            ("LinuxNativeAgent", lambda: self._safe_import_agent("agents.linux_native_agent", "LinuxNativeAgent")),
            
            # Specialized
            ("OpenCodeAgent", lambda: self._safe_import_agent("agents.opencode", "OpenCodeAgent", groq_client=groq_client)),
            ("GithubAgent", lambda: self._safe_import_agent("agents.github_agent", "GithubAgent")),
            ("BettingAnalystAgent", lambda: self._safe_import_agent("agents.betting_analyst", "BettingAnalystAgent")),
            
            # Economic Sentinel
            ("EconomicSentinel", lambda: self._safe_import_agent("agents.economic_sentinel", "EconomicSentinel")),
            
            # Long-term Memory
            ("SemanticMemoryWeaver", lambda: self._safe_import_agent("agents.semantic_memory_weaver", "SemanticMemoryWeaver", groq_client=groq_client)),
            
            # Omni-Channel
            ("OmniChannelStrategist", lambda: self._safe_import_agent("agents.omni_channel_strategist", "OmniChannelStrategist", message_bus=self.message_bus, groq_client=groq_client)),
            
            # Hardware Bridge (disabled: high CPU from aggressive GLib/pyudev polling)
            # ("HardwareSynergyBridge", lambda: self._safe_import_agent(
            #     "agents.hardware_synergy_bridge",
            #     "HardwareSynergyBridge",
            #     groq_client=groq_client,
            #     message_bus=self.message_bus,
            #     orchestrator=self.orchestrator
            # )),
            
            # DevOps
            ("AutonomousDevOpsRefactor", lambda: self._safe_import_agent(
                "agents.autonomous_devops_refactor",
                "AutonomousDevOpsRefactor",
                groq_client=groq_client,
                message_bus=self.message_bus,
                github_agent=self.orchestrator.get_agent("GithubAgent")
            )),
            
            # Skill Alchemist
            ("SkillAlchemist", lambda: self._safe_import_agent(
                "agents.skill_alchemist",
                "SkillAlchemist",
                orchestrator=self.orchestrator
            )),
            
            # Nexus Intelligence (SEMPRE POR ÚLTIMO)
            ("NexusIntelligence", lambda: self._safe_import_agent("agents.nexus_intelligence", "NexusIntelligence")),
        ]
    
    def _safe_import_agent(self, module_path: str, class_name: str, **kwargs) -> any:
        """
        Importa agente com tratamento de erro.
        
        Args:
            module_path: Caminho do módulo (ex: "agents.proactive")
            class_name: Nome da classe (ex: "ProactiveAgent")
            **kwargs: Argumentos para construtor do agente
        
        Returns:
            Instância do agente ou None se falhar
        """
        import importlib
        
        try:
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            return agent_class(**kwargs)
        except ImportError as e:
            logger.warning(f"Agente não disponível: {module_path}.{class_name} — {e}")
            # Retorna um stub/null object para graceful degradation
            return None
    
    async def _register_with_architect(self, agent_name: str, agent: any) -> None:
        """Registra agente com ArchitectAgent para orquestração."""
        if self.architect and agent:
            try:
                module_path = getattr(agent.__class__, "__module__", f"agents.{self._to_snake_case(agent_name)}")
                # Architect registra via register_agent
                await self.architect.register_agent(
                    name=agent_name,
                    module_path=module_path,
                    topics=[f"{agent_name.lower()}.command"]
                )
            except Exception as e:
                logger.debug(f"Não foi possível registrar {agent_name} no Architect: {e}")
    
    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Converte nome de agente para snake_case (ex: ArchitectAgent → architect_agent)."""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    async def _bootstrap_channels(self) -> None:
        """Registra canais de comunicação."""
        logger.info("Registrando canais...")
        
        try:
            from channels.telegram import TelegramChannel
            telegram_channel = TelegramChannel()
            self.orchestrator.register_channel(telegram_channel)
            logger.info("✅ TelegramChannel registrado.")
        except ImportError as e:
            logger.warning(f"TelegramChannel não disponível: {e}")
        except Exception as e:
            logger.error(f"Erro ao registrar TelegramChannel: {e}")
    
    async def start(self) -> None:
        """
        Inicia o sistema The Moon.
        
        Fluxo:
          1. Inicia Orchestrator (que inicia todos os agentes e canais)
          2. Inicia loops de background
          3. Configura handlers de shutdown
        """
        logger.info("🚀 Starting The Moon Ecosystem...")

        try:
            # Inicia Orchestrator (agentes, canais, loops)
            await self.orchestrator.start()

            # ── Hive: Colmeia de Agentes Especializados ──
            try:
                self.hive_integration = HiveIntegration(
                    orchestrator=self.orchestrator,
                    bus=self.message_bus,
                    llm=self.orchestrator.llm,
                )
                await self.hive_integration.start()
                logger.info("🐝 Hive integrada ao sistema Moon")
            except Exception as e:
                logger.error("❌ Hive falhou ao iniciar: %s", e)

            # ── Cyber-Agentic API Server ──
            try:
                import uvicorn
                from api.server import app as fastapi_app
                fastapi_app.state.orchestrator = self.orchestrator
                config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="warning")
                self._api_server = uvicorn.Server(config)
                self._api_server_task = asyncio.create_task(self._api_server.serve(), name="moon.api_server")
                logger.info("🌌 Cyber-Agentic API iniciada na porta 8000")
            except Exception as e:
                logger.error("❌ Cyber-Agentic API falhou ao iniciar: %s", e)

            self._initialized = True
            logger.info("✅ The Moon Ecosystem is ONLINE.")

        except Exception as e:
            logger.error(f"Erro ao iniciar sistema: {e}")
            raise
    
    async def stop(self) -> None:
        """
        Para o sistema com shutdown limpo.
        
        Fluxo:
          1. Dispara shutdown event
          2. Para Orchestrator (que para agentes e canais)
          3. Limpa recursos
        """
        logger.info("🛑 Stopping The Moon Ecosystem...")

        self._shutdown_event.set()

        try:
            # Para API Server
            if getattr(self, "_api_server", None):
                self._api_server.should_exit = True
            if getattr(self, "_api_server_task", None) and not self._api_server_task.done():
                self._api_server_task.cancel()

            # Para Hive primeiro (graceful shutdown dos 5 agentes)
            if self.hive_integration:
                await self.hive_integration.stop()

            # Para Orchestrator
            await self.orchestrator.stop()

            # Shutdown do Architect
            if self.architect:
                await self.architect.shutdown()

            logger.info("✅ The Moon Ecosystem stopped.")

        except Exception as e:
            logger.error(f"Erro durante shutdown: {e}")
            raise
    
    async def execute(self, task: str, agent: str, priority: AgentPriority = AgentPriority.MEDIUM, **kwargs):
        """
        Executa tarefa via Orchestrator.
        
        Args:
            task: Tarefa a executar
            agent: Nome do agente
            priority: Prioridade da tarefa
            **kwargs: Argumentos adicionais
        
        Returns:
            Resultado da execução
        """
        return await self.orchestrator.execute(task, agent_name=agent, priority=priority, **kwargs)
    
    def get_status(self) -> dict:
        """Retorna status do sistema."""
        return self.orchestrator.get_status()


# ─────────────────────────────────────────────────────────────
#  Signal Handlers
# ─────────────────────────────────────────────────────────────

def setup_signal_handlers(system: MoonSystem) -> None:
    """
    Configura handlers para SIGINT e SIGTERM.
    
    Permite shutdown limpo com Ctrl+C ou kill.
    """
    loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(_graceful_shutdown(system))
        )


async def _graceful_shutdown(system: MoonSystem) -> None:
    """
    Executa shutdown limpo do sistema.
    
    Args:
        system: Instância do MoonSystem
    """
    logger.info("Received shutdown signal — initiating graceful shutdown...")
    await system.stop()


# ─────────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────────

def run() -> None:
    """
    Ponto de entrada principal do The Moon Ecosystem.
    
    Fluxo:
      1. Bootstrap do sistema (logging, validação, agentes)
      2. Inicialização
      3. Loop principal (aguarda shutdown)
      4. Shutdown limpo
    """
    async def _run():
        try:
            # Bootstrap
            system = await bootstrap_system()
            
            # Setup signal handlers
            setup_signal_handlers(system)
            
            # Start
            await system.start()
            
            # Status
            status = system.get_status()
            logger.info(f"System Status: Agents={status.get('agents_online', 0)}, "
                       f"Skills={status.get('skills_online', 0)}, "
                       f"Channels={status.get('channels_online', 0)}")
            
            # Aguarda shutdown
            await system._shutdown_event.wait()
            
        except asyncio.CancelledError:
            logger.info("System shutdown requested.")
        except Exception as e:
            logger.error(f"System error: {e}", exc_info=True)
            raise
        finally:
            # Cleanup
            if 'system' in locals() and system._initialized:
                await system.stop()
    
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
