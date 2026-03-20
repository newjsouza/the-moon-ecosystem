"""
core/hive_integration.py
Integração da Hive com o sistema Moon existente.
Registra os 5 agentes da Colmeia no Orchestrator
sem modificar a estrutura central do sistema.
"""
import asyncio
import logging
from typing import Any

from core.hive import Hive
from core.message_bus import MessageBus
from agents.llm import LLMRouter

logger = logging.getLogger(__name__)


class HiveIntegration:
    """
    Ponte entre a Hive e o Orchestrator existente.
    Registra os agentes da colmeia no Orchestrator e
    garante inicialização/encerramento coordenados.

    Uso em main.py (MoonSystem):
        self.hive_integration = HiveIntegration(
            orchestrator=self.orchestrator,
            bus=self.bus,
            llm=self.llm,
        )
        await self.hive_integration.register()
        await self.hive_integration.start()
    """

    def __init__(self, orchestrator: Any, bus: MessageBus, llm: LLMRouter):
        self._orchestrator = orchestrator
        self._hive = Hive(bus=bus, llm=llm)
        self._registered = False
        self._started = False

    async def register(self) -> None:
        """Registra os 5 agentes da Hive no Orchestrator."""
        if self._registered:
            return
        # Inicializa internamente para criar as instâncias
        # (sem chamar start() ainda)
        from agents.scheduler_agent import SchedulerAgent
        from agents.memory_agent import MemoryAgent
        from agents.deep_web_research_agent import DeepWebResearchAgent
        from agents.data_pipeline_agent import DataPipelineAgent
        from agents.desktop_control_agent import DesktopControlAgent

        hive_agents = {
            "SchedulerAgent":       SchedulerAgent(),
            "MemoryAgent":          MemoryAgent(),
            "DeepWebResearchAgent": DeepWebResearchAgent(self._hive._bus, self._hive._llm),
            "DataPipelineAgent":    DataPipelineAgent(self._hive._bus, self._hive._llm),
            "DesktopControlAgent":  DesktopControlAgent(self._hive._bus, self._hive._llm),
        }

        # Reutiliza as instâncias na Hive para evitar duplicação
        self._hive._agents = hive_agents

        for name, agent in hive_agents.items():
            try:
                self._orchestrator.register_agent(agent)
                logger.info("  🐝 Hive: %s registrado no Orchestrator", name)
            except Exception as e:
                logger.warning("  ⚠️  Hive: falha ao registrar %s: %s", name, e)

        self._registered = True
        logger.info("🐝 Hive: todos os agentes registrados no Orchestrator")

    async def start(self) -> None:
        """Inicia a Hive (start de cada agente em ordem)."""
        if self._started:
            return
        if not self._registered:
            await self.register()
        await self._hive.start()
        self._started = True
        logger.info("🐝 Hive iniciada e integrada ao sistema Moon")

    async def stop(self) -> None:
        """Encerramento graceful da Hive."""
        if not self._started:
            return
        await self._hive.stop()
        self._started = False
        logger.info("🐝 Hive encerrada")

    async def status(self) -> dict:
        return await self._hive.status()

    @property
    def hive(self) -> Hive:
        return self._hive
