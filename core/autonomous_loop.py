"""
AutonomousLoop — self-driving execution engine for The Moon ecosystem.
Integrates: RAG (B) + Evaluator-Optimizer (C) + Streaming (D)
            + Text-to-SQL (E) + Observability (F) + CircuitBreaker (G)
Runs a priority task queue continuously with self-healing and persistence.
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional
from core.agent_base import TaskResult
from core.loop_task import LoopTask, TaskStatus
from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from core.observability.observer import MoonObserver

logger = logging.getLogger(__name__)

STATE_DIR = Path("data/loop_state")
CHECKPOINT_FILE = STATE_DIR / "checkpoints" / "loop_checkpoint.json"


class AutonomousLoop:
    """
    Self-driving task execution engine.
    Manages: task queue, circuit breakers, health checks, state persistence.

    Usage:
        loop = AutonomousLoop(orchestrator)
        loop.enqueue(LoopTask(agent_id="blog_writer", task="write post"))
        await loop.run(max_iterations=10)
    """

    DEFAULT_TICK_INTERVAL = 2.0    # seconds between queue checks
    MAX_CONCURRENT_TASKS = 3       # max parallel task executions
    HEALTH_CHECK_INTERVAL = 30     # seconds between health checks

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self._queue: list[LoopTask] = []
        self._completed: list[LoopTask] = []
        self._failed: list[LoopTask] = []
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._running = False
        self._iteration = 0
        self._last_health_check = 0.0
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_TASKS)
        self.observer = MoonObserver.get_instance()
        self.logger = logging.getLogger(self.__class__.__name__)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "queues").mkdir(exist_ok=True)
        (STATE_DIR / "checkpoints").mkdir(exist_ok=True)

    # ──────────────────────────────────────────────────────────────
    # Config loading
    # ──────────────────────────────────────────────────────────────

    def load_config(self, config_path: str = "config/autonomous_loop.json") -> int:
        """
        Load tasks from JSON config file and enqueue enabled tasks.
        Returns the number of tasks loaded.
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                self.logger.warning(f"Config file not found: {config_path}")
                return 0

            with open(config_file) as f:
                config = json.load(f)

            tasks_loaded = 0
            for task_cfg in config.get("tasks", []):
                if task_cfg.get("enabled", False):
                    task = LoopTask(
                        task_id=task_cfg.get("id", f"task_{tasks_loaded}"),
                        agent_id=task_cfg.get("agent_id", "unknown"),
                        task=task_cfg.get("task", ""),
                        kwargs=task_cfg.get("kwargs", {}),
                        priority=task_cfg.get("priority", 5),
                        domain=task_cfg.get("domain", "general"),
                        use_evaluator=task_cfg.get("use_evaluator", False),
                        max_retries=task_cfg.get("max_retries", 3),
                    )
                    self.enqueue(task)
                    tasks_loaded += 1

            self.logger.info(f"Loaded {tasks_loaded} tasks from {config_path}")
            return tasks_loaded

        except Exception as e:
            self.logger.error(f"Failed to load config from {config_path}: {e}")
            return 0

    # ──────────────────────────────────────────────────────────────
    # Queue management
    # ──────────────────────────────────────────────────────────────

    def enqueue(self, task: LoopTask) -> None:
        """Add task to queue. Sorted by priority (lower = higher priority)."""
        self._queue.append(task)
        self._queue.sort(key=lambda t: t.priority)
        self.logger.info(
            f"Enqueued: [{task.task_id}] agent={task.agent_id} "
            f"priority={task.priority} queue_size={len(self._queue)}"
        )

    def enqueue_many(self, tasks: list[LoopTask]) -> None:
        for task in tasks:
            self._queue.append(task)
        self._queue.sort(key=lambda t: t.priority)

    def dequeue(self) -> Optional[LoopTask]:
        """Get next pending task, respecting circuit breakers."""
        for task in self._queue:
            if task.status != TaskStatus.PENDING:
                continue
            cb = self._get_circuit_breaker(task.agent_id)
            if cb.is_open:
                task.mark_skipped(f"Circuit breaker OPEN for {task.agent_id}")
                self._queue.remove(task)
                self._failed.append(task)
                self.logger.warning(
                    f"Task [{task.task_id}] skipped — CB open for {task.agent_id}"
                )
                continue
            self._queue.remove(task)
            return task
        return None

    def queue_size(self) -> int:
        return len([t for t in self._queue if t.status == TaskStatus.PENDING])

    # ──────────────────────────────────────────────────────────────
    # Circuit breakers
    # ──────────────────────────────────────────────────────────────

    def _get_circuit_breaker(self, agent_id: str) -> CircuitBreaker:
        if agent_id not in self._circuit_breakers:
            self._circuit_breakers[agent_id] = CircuitBreaker(
                agent_id,
                CircuitBreakerConfig(
                    failure_threshold=5,
                    recovery_timeout=60.0,
                    success_threshold=2,
                    timeout=30.0
                )
            )
        return self._circuit_breakers[agent_id]

    def get_circuit_status(self) -> dict:
        return {
            aid: cb.get_status()
            for aid, cb in self._circuit_breakers.items()
        }

    # ──────────────────────────────────────────────────────────────
    # Execution
    # ──────────────────────────────────────────────────────────────

    async def run(self, max_iterations: int = None,
                  tick_interval: float = None) -> TaskResult:
        """
        Start the autonomous loop.
        Runs until: queue empty OR max_iterations reached OR stop() called.
        """
        start = time.time()
        tick = tick_interval or self.DEFAULT_TICK_INTERVAL
        self._running = True
        self._iteration = 0

        self.logger.info(
            f"AutonomousLoop starting — "
            f"queue={self.queue_size()} max_iter={max_iterations}"
        )

        try:
            while self._running:
                if max_iterations and self._iteration >= max_iterations:
                    self.logger.info(
                        f"Max iterations ({max_iterations}) reached — stopping"
                    )
                    break

                if self.queue_size() == 0:
                    self.logger.info("Queue empty — loop idle")
                    break

                self._iteration += 1
                await self._tick()
                await self._maybe_health_check()
                await asyncio.sleep(tick)

        except asyncio.CancelledError:
            self.logger.info("AutonomousLoop cancelled")
        except Exception as e:
            self.logger.error(f"AutonomousLoop error: {e}")
        finally:
            self._running = False
            await self.persist_state()

        elapsed = time.time() - start
        self.logger.info(
            f"AutonomousLoop finished — "
            f"iterations={self._iteration} "
            f"completed={len(self._completed)} "
            f"failed={len(self._failed)} "
            f"elapsed={elapsed:.1f}s"
        )
        return TaskResult(
            success=True,
            data={
                "iterations": self._iteration,
                "completed": len(self._completed),
                "failed": len(self._failed),
                "elapsed_seconds": round(elapsed, 2),
            },
            execution_time=elapsed
        )

    async def _tick(self) -> None:
        """Process one batch of tasks from the queue."""
        tasks_this_tick = []
        while len(tasks_this_tick) < self.MAX_CONCURRENT_TASKS:
            task = self.dequeue()
            if task is None:
                break
            tasks_this_tick.append(task)

        if not tasks_this_tick:
            return

        self.logger.debug(
            f"Tick #{self._iteration}: executing {len(tasks_this_tick)} tasks"
        )
        await asyncio.gather(
            *[self._execute_task(t) for t in tasks_this_tick],
            return_exceptions=True
        )

    async def _execute_task(self, task: LoopTask) -> None:
        """Execute a single task with circuit breaker + observability."""
        async with self._semaphore:
            task.mark_running()
            cb = self._get_circuit_breaker(task.agent_id)

            self.logger.info(
                f"Executing [{task.task_id}] agent={task.agent_id} "
                f"task='{task.task[:50]}'"
            )

            try:
                if self.orchestrator:
                    result = await cb.call(
                        self.orchestrator._call_agent,
                        task.agent_id,
                        task.task,
                        **task.kwargs
                    )
                else:
                    # Fallback: direct execution without orchestrator
                    result = await self._direct_execute(task, cb)

                if result.success:
                    task.mark_completed(str(result.data)[:200])
                    self._completed.append(task)
                    self.logger.info(
                        f"Task [{task.task_id}] COMPLETED ✅ "
                        f"in {task.execution_time:.2f}s"
                    )
                    # Publish event for CodexUpdaterAgent
                    from core.message_bus import MessageBus
                    bus = MessageBus()
                    await bus.publish(
                        sender="autonomous_loop",
                        topic="autonomous_loop.task_completed",
                        payload={
                            "type": "feat",
                            "title": task.task[:80],
                            "agent_id": task.agent_id,
                            "details": result.data or {},
                        }
                    )
                    # Optional: run through EvaluatorAgent
                    if task.use_evaluator and result.data:
                        await self._evaluate_result(task, result)
                else:
                    await self._handle_failure(task, result.error or "Unknown error")

            except Exception as e:
                await self._handle_failure(task, str(e))

    async def _direct_execute(self, task: LoopTask,
                               cb: CircuitBreaker) -> TaskResult:
        """Execute task without orchestrator (fallback mode)."""
        # This is a fallback implementation for when no orchestrator is available
        return TaskResult(
            success=False,
            error="No orchestrator provided for task execution",
            execution_time=0.0
        )

    async def _handle_failure(self, task: LoopTask, error: str) -> None:
        """Handle task failure with retry logic."""
        task.mark_failed(error)
        self.logger.warning(
            f"Task [{task.task_id}] FAILED "
            f"(attempt {task.retry_count}/{task.max_retries}): {error[:80]}"
        )
        if task.is_retryable:
            task.status = TaskStatus.PENDING
            task.error = None
            self.enqueue(task)
            self.logger.info(
                f"Task [{task.task_id}] re-queued "
                f"(retry {task.retry_count}/{task.max_retries})"
            )
        else:
            self._failed.append(task)
            self.logger.error(
                f"Task [{task.task_id}] permanently failed "
                f"after {task.retry_count} retries"
            )

    async def _evaluate_result(self, task: LoopTask,
                                result: TaskResult) -> None:
        """Optionally evaluate task result via EvaluatorAgent."""
        try:
            # Attempt to get evaluator from orchestrator
            if self.orchestrator and "EvaluatorAgent" in self.orchestrator._agents:
                evaluator_agent = self.orchestrator._agents["EvaluatorAgent"]
                eval_result = await evaluator_agent._execute(
                    task="evaluate result",
                    result_data=str(result.data)[:500],
                    domain=task.domain,
                    original_task=task.task,
                    agent_id=task.agent_id
                )
                
                if eval_result.success:
                    score = eval_result.data.get("score", 0)
                    passed = eval_result.data.get("passed", True)
                    self.logger.info(
                        f"Task [{task.task_id}] evaluation: "
                        f"score={score:.2f} {'✅' if passed else '⚠️'}"
                    )
        except Exception as e:
            self.logger.debug(f"Evaluation skipped: {e}")

    # ──────────────────────────────────────────────────────────────
    # Health + self-healing
    # ──────────────────────────────────────────────────────────────

    async def _maybe_health_check(self) -> None:
        """Run health check if interval has elapsed."""
        now = time.time()
        if now - self._last_health_check < self.HEALTH_CHECK_INTERVAL:
            return
        self._last_health_check = now
        await self._health_check()

    async def _health_check(self) -> None:
        """Check system health and attempt self-healing."""
        report = await self.observer.health_report()
        system_status = report.get("system_status", "healthy")

        self.logger.info(
            f"Health check: status={system_status} "
            f"agents={len(report.get('agents', {}))} "
            f"success_rate={report.get('overall_success_rate', 1.0):.0%}"
        )

        if system_status == "critical":
            self.logger.warning(
                "System status CRITICAL — pausing queue for 30s"
            )
            await asyncio.sleep(30)

        # Reset circuit breakers that have recovered
        for agent_id, cb in self._circuit_breakers.items():
            if cb.state.value == "half_open":
                self.logger.info(
                    f"Self-healing: {agent_id} circuit in HALF_OPEN — monitoring"
                )

    # ──────────────────────────────────────────────────────────────
    # State persistence
    # ──────────────────────────────────────────────────────────────

    async def persist_state(self) -> None:
        """Save current loop state to JSON checkpoint."""
        try:
            checkpoint = {
                "iteration": self._iteration,
                "timestamp": time.time(),
                "queue": [t.to_dict() for t in self._queue],
                "completed_count": len(self._completed),
                "failed_count": len(self._failed),
                "circuit_breakers": self.get_circuit_status(),
            }
            CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump(checkpoint, f, indent=2, default=str)
            self.logger.info(f"Loop state persisted: {CHECKPOINT_FILE}")
        except Exception as e:
            self.logger.error(f"Failed to persist state: {e}")

    async def restore_state(self) -> bool:
        """Restore pending tasks from last checkpoint."""
        try:
            if not CHECKPOINT_FILE.exists():
                return False
            with open(CHECKPOINT_FILE) as f:
                checkpoint = json.load(f)
            pending = [
                LoopTask.from_dict(t)
                for t in checkpoint.get("queue", [])
                if t.get("status") == "pending"
            ]
            if pending:
                self.enqueue_many(pending)
                self.logger.info(
                    f"Restored {len(pending)} pending tasks from checkpoint"
                )
            return True
        except Exception as e:
            self.logger.warning(f"Could not restore state: {e}")
            return False

    def stop(self) -> None:
        """Signal the loop to stop after current iteration."""
        self._running = False
        self.logger.info("AutonomousLoop stop requested")

    def get_status(self) -> dict:
        """Current loop status snapshot."""
        return {
            "running": self._running,
            "iteration": self._iteration,
            "queue_size": self.queue_size(),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "circuit_breakers": self.get_circuit_status(),
        }


# Preserve the original MoonSleepManager class for backward compatibility
"""
core/autonomous_loop.py
Manages the background research cycles.
Connected to the Orchestrator for channel broadcasts.

Updated: Moon-Stack QA automático integrado (FASE 6)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.orchestrator import Orchestrator

logger = logging.getLogger("moon.core.autonomous_loop")


class MoonSleepManager:
    """
    The autonomous research engine.
    Runs in the background, researching topics and pushing
    findings through the Orchestrator's channels.
    """

    def __init__(self, orchestrator: Optional["Orchestrator"] = None, topics: Optional[List[str]] = None):
        self.orchestrator = orchestrator
        self.topics = topics or [
            "GitHub open-source AI automation tools",
            "Machine Learning innovation 2026",
            "Autonomous Skill Agents development",
            "Multi-Agent System orchestration frameworks",
            "New AI reasoning techniques (innovation-focused)"
        ]
        self.is_running = False
        self.cycle_count = 0

        # Moon-Stack QA Settings
        self.qa_interval_hours = 6  # QA automático a cada 6 horas
        self._qa_task: Optional[asyncio.Task] = None

    async def start_cycle(self, interval_minutes: int = 60) -> None:
        self.is_running = True
        logger.info(f"Starting autonomous research loop. Interval: {interval_minutes}m")

        # Start QA scheduled loop
        await self._start_qa_loop()

        try:
            while self.is_running:
                self.cycle_count += 1
                logger.info(f"=== Research Cycle #{self.cycle_count} ===")

                findings = []
                for topic in self.topics:
                    if not self.is_running:
                        break

                    logger.info(f"CYCLE: Investigating '{topic}'")

                    # Try to use the ResearcherAgent if orchestrator is available
                    if self.orchestrator and "ResearcherAgent" in self.orchestrator._agents:
                        try:
                            res = await self.orchestrator._agents["ResearcherAgent"].execute(
                                topic, action="research"
                            )
                            if res.success:
                                findings.append(f"✅ {topic}")
                                logger.info(f"CYCLE SUCCESS: {topic}")
                            else:
                                findings.append(f"⚠️ {topic}: {res.error}")
                                logger.error(f"CYCLE ERROR: {topic}: {res.error}")
                        except Exception as e:
                            findings.append(f"❌ {topic}: {e}")
                            logger.error(f"CYCLE EXCEPTION: {topic}: {e}")
                    else:
                        findings.append(f"📋 {topic} (pesquisa pendente)")

                    # Pause between topics
                    await asyncio.sleep(30)

                # Broadcast findings via channels
                if self.orchestrator and findings:
                    now = datetime.now().strftime("%H:%M")
                    report = (
                        f"🔬 *Pesquisa Autônoma — Ciclo #{self.cycle_count}*\n"
                        f"🕐 {now}\n\n" +
                        "\n".join(findings) +
                        f"\n\n_Próximo ciclo em {interval_minutes} minutos._"
                    )
                    await self.orchestrator.broadcast(report)

                logger.info(f"Cycle #{self.cycle_count} complete. Resting for {interval_minutes} minutes...")
                await asyncio.sleep(interval_minutes * 60)

        except asyncio.CancelledError:
            logger.info("Autonomous loop cancelled gracefully.")
        except Exception as e:
            logger.error(f"Autonomous loop crashed: {e}")
        finally:
            self.is_running = False
            self.stop_qa_loop()

    async def _start_qa_loop(self) -> None:
        """Inicia loop de QA automático do Moon-Stack."""
        async def qa_cycle():
            logger.info(f"Moon-Stack QA started (interval: {self.qa_interval_hours}h)")

            while self.is_running:
                await asyncio.sleep(self.qa_interval_hours * 3600)

                if not self.is_running:
                    break

                logger.info("=== Moon-Stack QA Cycle ===")

                try:
                    # Run QA via MoonQAAgent if available
                    if self.orchestrator and "MoonQAAgent" in self.orchestrator._agents:
                        qa_agent = self.orchestrator._agents["MoonQAAgent"]
                        result = await qa_agent.execute("diff-aware")

                        if result.success:
                            health = result.data.get("overall_health", 0)
                            apps = result.data.get("apps_tested", [])

                            # Report via MessageBus
                            from core.message_bus import MessageBus
                            message_bus = MessageBus()
                            await message_bus.publish(
                                sender="AutonomousLoop",
                                topic="qa.scheduled",
                                payload={
                                    "health": health,
                                    "apps_tested": apps,
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )

                            logger.info(f"QA completed: health={health}, apps={apps}")
                        else:
                            logger.warning(f"QA failed: {result.error}")
                    else:
                        logger.debug("MoonQAAgent not available for scheduled QA")

                except Exception as e:
                    logger.error(f"Scheduled QA failed: {e}")

        self._qa_task = asyncio.create_task(qa_cycle(), name="moon.qa.autonomous")

    def stop_qa_loop(self) -> None:
        """Para o loop de QA automático."""
        if self._qa_task and not self._qa_task.done():
            self._qa_task.cancel()
            logger.info("Moon-Stack QA loop stopped.")

    def stop(self) -> None:
        self.is_running = False
        logger.info("Stopping autonomous loop.")
        self.stop_qa_loop()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    manager = MoonSleepManager()
    try:
        loop.run_until_complete(manager.start_cycle(interval_minutes=1))
    except KeyboardInterrupt:
        manager.stop()