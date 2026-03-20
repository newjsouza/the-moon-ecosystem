"""
core/hive.py — HiveOrchestrator
Inicializa e coordena os 5 agentes da Colmeia Moon.
Integra com o Orchestrator existente sem modificá-lo.
Um único ponto de entrada: await Hive.start()
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from core.message_bus import MessageBus
from agents.llm import LLMRouter
from agents.scheduler_agent import SchedulerAgent
from agents.memory_agent import MemoryAgent
from agents.deep_web_research_agent import DeepWebResearchAgent
from agents.data_pipeline_agent import DataPipelineAgent
from agents.desktop_control_agent import DesktopControlAgent

logger = logging.getLogger(__name__)


class Hive:
    """
    Colmeia Moon — coordenação dos 5 agentes especializados.
    Não substitui o Orchestrator existente; coexiste com ele
    via MessageBus compartilhado.

    Uso:
        hive = Hive(bus=bus, llm=llm)
        await hive.start()           # inicia todos os agentes
        await hive.status()          # health da colmeia
        await hive.stop()            # encerramento graceful
    """

    def __init__(self, bus: MessageBus, llm: LLMRouter):
        self._bus = bus
        self._llm = llm
        self._agents: dict[str, Any] = {}
        self._tasks: list[asyncio.Task] = []
        self._started_at: datetime | None = None
        self._running = False

    # ─────────────────────────────────────────────
    # CICLO DE VIDA
    # ─────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            logger.warning("Hive já está em execução")
            return

        logger.info("🐝 Iniciando The Moon Hive...")
        self._started_at = datetime.now(timezone.utc)

        self._agents = {
            "SchedulerAgent":        SchedulerAgent(self._bus, self._llm),
            "MemoryAgent":           MemoryAgent(self._bus, self._llm),
            "DeepWebResearchAgent":  DeepWebResearchAgent(self._bus, self._llm),
            "DataPipelineAgent":     DataPipelineAgent(self._bus, self._llm),
            "DesktopControlAgent":   DesktopControlAgent(self._bus, self._llm),
        }

        # Ordem de inicialização importa:
        # 1. MemoryAgent primeiro — outros dependem de memory.store
        # 2. DataPipelineAgent — depende indiretamente de MemoryAgent
        # 3. DeepWebResearchAgent — publica em memory.store
        # 4. DesktopControlAgent — independente
        # 5. SchedulerAgent por último — dispara eventos para todos
        init_order = [
            "MemoryAgent",
            "DataPipelineAgent",
            "DeepWebResearchAgent",
            "DesktopControlAgent",
            "SchedulerAgent",
        ]

        for name in init_order:
            agent = self._agents[name]
            try:
                task = asyncio.create_task(
                    agent.start(), name=f"hive.{name}"
                )
                self._tasks.append(task)
                logger.info("  ✅ %s iniciado", name)
                await asyncio.sleep(0.1)  # pequena pausa entre inits
            except Exception as e:
                logger.error("  ❌ %s falhou ao iniciar: %s", name, e)

        self._running = True

        await self._bus.publish(
            "Hive", "hive.heartbeat",
            {
                "event": "hive_started",
                "agents": list(self._agents.keys()),
                "timestamp": self._started_at.isoformat(),
            },
        )
        logger.info("🐝 Hive iniciada — %d agentes ativos", len(self._agents))

    async def stop(self) -> None:
        if not self._running:
            return
        logger.info("🐝 Encerrando Hive...")

        # Encerrar DataPipelineAgent gracefully (fecha DuckDB)
        dp = self._agents.get("DataPipelineAgent")
        if dp and hasattr(dp, "close"):
            try:
                await dp.close()
                logger.info("  ✅ DataPipelineAgent encerrado")
            except Exception as e:
                logger.warning("  ⚠️  DataPipelineAgent close: %s", e)

        # Cancelar todas as tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        self._running = False
        self._tasks.clear()
        logger.info("🐝 Hive encerrada")

    # ─────────────────────────────────────────────
    # STATUS / HEALTH
    # ─────────────────────────────────────────────

    async def status(self) -> dict:
        uptime = None
        if self._started_at:
            delta = datetime.now(timezone.utc) - self._started_at
            uptime = int(delta.total_seconds())

        agent_status = {}
        for name, agent in self._agents.items():
            try:
                result = await asyncio.wait_for(
                    agent._execute("status"), timeout=5.0
                )
                agent_status[name] = {
                    "ok": result.success,
                    "data": result.data,
                }
            except asyncio.TimeoutError:
                agent_status[name] = {"ok": False, "data": {"error": "timeout"}}
            except Exception as e:
                agent_status[name] = {"ok": False, "data": {"error": str(e)}}

        healthy = sum(1 for s in agent_status.values() if s["ok"])
        return {
            "running": self._running,
            "uptime_seconds": uptime,
            "agents_total": len(self._agents),
            "agents_healthy": healthy,
            "agents": agent_status,
        }

    # ─────────────────────────────────────────────
    # ATALHOS DE ACESSO AOS AGENTES
    # ─────────────────────────────────────────────

    @property
    def scheduler(self) -> SchedulerAgent:
        return self._agents["SchedulerAgent"]

    @property
    def memory(self) -> MemoryAgent:
        return self._agents["MemoryAgent"]

    @property
    def researcher(self) -> DeepWebResearchAgent:
        return self._agents["DeepWebResearchAgent"]

    @property
    def pipeline(self) -> DataPipelineAgent:
        return self._agents["DataPipelineAgent"]

    @property
    def desktop(self) -> DesktopControlAgent:
        return self._agents["DesktopControlAgent"]

    def get_agent(self, name: str) -> Any:
        agent = self._agents.get(name)
        if not agent:
            raise KeyError(f"Agente '{name}' não encontrado na Hive. "
                           f"Disponíveis: {list(self._agents.keys())}")
        return agent
