"""
agents/scheduler_agent.py
SchedulerAgent — Rainha da Colmeia.
Orquestra ciclos temporais, dispara eventos no MessageBus
e monitora saúde de todos os agentes via hive.heartbeat.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.agent_base import AgentBase, TaskResult
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)


class SchedulerAgent(AgentBase):
    """
    Rainha da Colmeia.
    Orquestra ciclos temporais, dispara eventos no MessageBus
    e monitora saúde de todos os agentes via hive.heartbeat.
    """

    def __init__(self):
        super().__init__()
        self.name = "SchedulerAgent"
        self.description = "Orquestra ciclos temporais e monitora saúde dos agentes"
        self._scheduler = AsyncScheduler()
        self._heartbeats: dict[str, datetime] = {}
        self._registered_jobs: list[str] = []
        self._bus = MessageBus()

    async def initialize(self) -> None:
        """Inicializa o SchedulerAgent e registra jobs padrão."""
        await super().initialize()
        await self._register_default_jobs()
        logger.info("SchedulerAgent inicializado com %d jobs", len(self._registered_jobs))

    async def start(self) -> None:
        """Inicia o loop do scheduler."""
        await self._bus.subscribe("hive.heartbeat", self._on_heartbeat_wrapper)
        
        async with self._scheduler:
            await self._scheduler.start()
            logger.info("SchedulerAgent iniciado")
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("SchedulerAgent sendo encerrado...")

    async def _register_default_jobs(self) -> None:
        """Registra jobs padrão: health_check, daily_research, memory_sync."""
        # Heartbeat check a cada 2 minutos
        await self._scheduler.add_schedule(
            self._emit_health_check,
            IntervalTrigger(minutes=2),
            id="health_check",
        )
        # Research diário de tecnologia às 06:00
        await self._scheduler.add_schedule(
            self._emit_daily_research,
            CronTrigger(hour=6, minute=0),
            id="daily_research",
        )
        # Sincronização de memória a cada hora
        await self._scheduler.add_schedule(
            self._emit_memory_sync,
            IntervalTrigger(hours=1),
            id="memory_sync",
        )
        self._registered_jobs = ["health_check", "daily_research", "memory_sync"]

    async def add_cron_job(self, job_id: str, cron_expr: str, topic: str, payload: dict) -> None:
        """Adiciona job cron dinamicamente. cron_expr: '0 8 * * *' (min, hora, dia, mês, dow)."""
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression inválido: {cron_expr}. Esperado 5 partes.")
        
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        
        async def _emit():
            await self._bus.publish("SchedulerAgent", topic, payload)
        
        await self._scheduler.add_schedule(_emit, trigger, id=job_id)
        self._registered_jobs.append(job_id)
        logger.info("Job '%s' registrado: %s → %s", job_id, cron_expr, topic)

    async def remove_job(self, job_id: str) -> None:
        """Remove um job registrado."""
        await self._scheduler.remove_schedule(job_id)
        self._registered_jobs = [j for j in self._registered_jobs if j != job_id]
        logger.info("Job '%s' removido", job_id)

    async def list_jobs(self) -> list[str]:
        """Lista todos os jobs registrados."""
        return list(self._registered_jobs)

    async def _emit_health_check(self) -> None:
        """Emite evento de health check e identifica agentes offline."""
        now = datetime.now(timezone.utc)
        offline = [
            name for name, last in self._heartbeats.items()
            if (now - last).total_seconds() > 300
        ]
        await self._bus.publish(
            "SchedulerAgent", "scheduler.tick",
            {"event": "health_check", "offline_agents": offline, "timestamp": now.isoformat()}
        )
        if offline:
            logger.warning("Agentes sem heartbeat: %s", offline)

    async def _emit_daily_research(self) -> None:
        """Emite request de pesquisa diária de tecnologia."""
        await self._bus.publish(
            "SchedulerAgent", "research.request",
            {
                "query": "latest open source LLM tools, AI agents, Python libraries 2026",
                "sources": ["github", "huggingface", "arxiv"],
                "depth": "deep",
                "save_to_memory": True,
            }
        )
        logger.info("Daily research request emitido")

    async def _emit_memory_sync(self) -> None:
        """Emite evento de sincronização de memória."""
        await self._bus.publish(
            "SchedulerAgent", "memory.store",
            {"event": "sync", "timestamp": datetime.now(timezone.utc).isoformat()}
        )

    async def _on_heartbeat_wrapper(self, message: Any) -> None:
        """Wrapper para receber mensagens do tópico hive.heartbeat."""
        sender = getattr(message, 'sender', 'unknown')
        payload = getattr(message, 'payload', {})
        await self._on_heartbeat(sender, payload)

    async def _on_heartbeat(self, sender: str, payload: dict) -> None:
        """Atualiza último heartbeat de um agente."""
        self._heartbeats[sender] = datetime.now(timezone.utc)
        logger.debug("Heartbeat recebido de %s", sender)

    async def _execute(self, task: str, **kwargs: Any) -> TaskResult:
        """Executa tarefas de gerenciamento de jobs."""
        start = time.time()
        try:
            if task == "add_job":
                job_id = kwargs.get("job_id")
                cron_expr = kwargs.get("cron_expr")
                topic = kwargs.get("topic")
                payload = kwargs.get("payload", {})
                if not all([job_id, cron_expr, topic]):
                    return TaskResult(
                        success=False,
                        error="add_job requer job_id, cron_expr, topic",
                        execution_time=time.time() - start
                    )
                await self.add_cron_job(job_id, cron_expr, topic, payload)
                return TaskResult(
                    success=True,
                    data={"job_id": job_id},
                    execution_time=time.time() - start
                )
            
            if task == "remove_job":
                job_id = kwargs.get("job_id")
                if not job_id:
                    return TaskResult(
                        success=False,
                        error="remove_job requer job_id",
                        execution_time=time.time() - start
                    )
                await self.remove_job(job_id)
                return TaskResult(
                    success=True,
                    data={"removed": job_id},
                    execution_time=time.time() - start
                )
            
            if task == "list_jobs":
                jobs = await self.list_jobs()
                return TaskResult(
                    success=True,
                    data={"jobs": jobs},
                    execution_time=time.time() - start
                )
            
            return TaskResult(
                success=False,
                error=f"Task desconhecida: {task}",
                execution_time=time.time() - start
            )
        
        except Exception as e:
            logger.exception("SchedulerAgent._execute falhou")
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )
