"""
MoonDaemon — runs AutonomousLoop as a long-lived daemon process.
Handles SIGTERM/SIGINT for graceful shutdown.
Registers default recurring tasks (sports reports, blog generation).
"""
import asyncio
import logging
import signal
import time
from core.autonomous_loop import AutonomousLoop
from core.loop_task import LoopTask
from core.observability.observer import MoonObserver

logger = logging.getLogger(__name__)


class MoonDaemon:
    """
    Production daemon for The Moon ecosystem.
    Usage: await MoonDaemon().start()
    """

    HEARTBEAT_INTERVAL = 60  # seconds between heartbeat logs

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self.loop = AutonomousLoop(orchestrator)
        self.observer = MoonObserver.get_instance()
        self._shutdown_event = asyncio.Event()
        self.logger = logging.getLogger(self.__class__.__name__)

    def _register_signals(self) -> None:
        """Register SIGTERM and SIGINT for graceful shutdown."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(
                        self._handle_shutdown(s)
                    )
                )
            except NotImplementedError:
                # Windows — signals not fully supported
                signal.signal(sig, lambda s, f: asyncio.create_task(
                    self._handle_shutdown(s)
                ))

    async def _handle_shutdown(self, sig) -> None:
        """Graceful shutdown: drain queue → persist state → exit."""
        self.logger.info(
            f"Received {sig.name} — initiating graceful shutdown..."
        )
        self.loop.stop()
        self._shutdown_event.set()

    def _register_default_tasks(self) -> None:
        """Register standard recurring tasks."""
        from core.sports_config import DEFAULT_COMPETITIONS

        # Weekly sports reports for default competitions
        for i, competition in enumerate(DEFAULT_COMPETITIONS):
            self.loop.enqueue(LoopTask(
                agent_id="sports_analytics",
                task="report",
                kwargs={"competition": competition, "dry_run": False},
                priority=5 + i,
                domain="general",
                use_evaluator=False,
                max_retries=2,
            ))
            self.logger.info(
                f"Scheduled sports report: {competition}"
            )

    async def _heartbeat(self) -> None:
        """Periodic status log."""
        while not self._shutdown_event.is_set():
            status = self.loop.get_status()
            report = await self.observer.health_report()
            self.logger.info(
                f"💓 Heartbeat | "
                f"queue={status['queue_size']} "
                f"completed={status['completed']} "
                f"failed={status['failed']} "
                f"health={report.get('system_status', 'unknown')}"
            )
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def start(self, with_default_tasks: bool = True) -> None:
        """Start the daemon — blocks until shutdown signal."""
        self.logger.info("🌙 The Moon Daemon starting...")
        self._register_signals()

        if with_default_tasks:
            self._register_default_tasks()

        # Restore pending tasks from last checkpoint
        restored = await self.loop.restore_state()
        if restored:
            self.logger.info("Restored tasks from checkpoint ✅")

        # Run heartbeat and loop concurrently
        heartbeat_task = asyncio.create_task(self._heartbeat())
        loop_task = asyncio.create_task(
            self.loop.run(max_iterations=None)
        )

        self.logger.info(
            f"🌙 The Moon Daemon running | "
            f"queue={self.loop.queue_size()} tasks"
        )

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        self.logger.info("Shutting down — persisting state...")
        heartbeat_task.cancel()
        loop_task.cancel()

        try:
            await asyncio.wait_for(
                asyncio.gather(heartbeat_task, loop_task,
                               return_exceptions=True),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            self.logger.warning("Shutdown timeout — forcing exit")

        await self.loop.persist_state()
        await self.observer.persist_session()
        self.logger.info("🌙 The Moon Daemon stopped gracefully ✅")