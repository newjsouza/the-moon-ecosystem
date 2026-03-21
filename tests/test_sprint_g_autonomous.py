"""Sprint G — Test suite for AutonomousLoop, CircuitBreaker, LoopTask."""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# CircuitBreaker tests
# ─────────────────────────────────────────────
class TestCircuitBreaker:

    def setup_method(self):
        from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        self.cb = CircuitBreaker("test_agent", CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=5.0,
            success_threshold=2,
            timeout=10.0
        ))

    def test_initial_state_closed(self):
        from core.circuit_breaker import CircuitState
        assert self.cb.state == CircuitState.CLOSED
        assert not self.cb.is_open

    def test_transitions_to_open_after_threshold(self):
        from core.circuit_breaker import CircuitState
        for _ in range(3):
            self.cb._on_failure()
        assert self.cb.state == CircuitState.OPEN
        assert self.cb.is_open

    def test_open_to_half_open_after_timeout(self):
        from core.circuit_breaker import CircuitState
        for _ in range(3):
            self.cb._on_failure()
        self.cb._last_failure_time = time.time() - 10.0  # simulate elapsed timeout
        assert self.cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_after_successes(self):
        from core.circuit_breaker import CircuitState
        for _ in range(3):
            self.cb._on_failure()
        self.cb._last_failure_time = time.time() - 10.0
        _ = self.cb.state  # trigger transition to HALF_OPEN
        self.cb._on_success()
        self.cb._on_success()
        assert self.cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        from core.circuit_breaker import CircuitState
        for _ in range(3):
            self.cb._on_failure()
        self.cb._last_failure_time = time.time() - 10.0
        _ = self.cb.state  # HALF_OPEN
        self.cb._on_failure()
        assert self.cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_call_open_returns_error_task_result(self):
        for _ in range(3):
            self.cb._on_failure()
        result = await self.cb.call(AsyncMock(return_value=TaskResult(success=True)))
        assert isinstance(result, TaskResult)
        assert result.success is False
        assert "OPEN" in result.error

    @pytest.mark.asyncio
    async def test_call_success_returns_result(self):
        async def mock_func():
            return TaskResult(success=True, data={"ok": True})
        result = await self.cb.call(mock_func)
        assert isinstance(result, TaskResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_call_timeout_returns_error(self):
        async def slow_func():
            await asyncio.sleep(100)
            return TaskResult(success=True)
        from core.circuit_breaker import CircuitBreakerConfig
        cb = __import__('core.circuit_breaker', fromlist=['CircuitBreaker']).CircuitBreaker(
            "slow", CircuitBreakerConfig(timeout=0.01)
        )
        result = await cb.call(slow_func)
        assert result.success is False
        assert "Timeout" in result.error

    def test_reset_clears_state(self):
        from core.circuit_breaker import CircuitState
        for _ in range(3):
            self.cb._on_failure()
        assert self.cb.state == CircuitState.OPEN
        self.cb.reset()
        assert self.cb.state == CircuitState.CLOSED
        assert self.cb._failure_count == 0

    def test_get_status_structure(self):
        status = self.cb.get_status()
        assert "name" in status
        assert "state" in status
        assert "failure_count" in status
        assert "time_until_recovery" in status


# ─────────────────────────────────────────────
# LoopTask tests
# ─────────────────────────────────────────────
class TestLoopTask:

    def setup_method(self):
        from core.loop_task import LoopTask
        self.task = LoopTask(
            agent_id="blog_writer",
            task="write post about The Moon",
            priority=3,
            max_retries=2,
            domain="blog"
        )

    def test_instantiation(self):
        assert self.task.agent_id == "blog_writer"
        assert self.task.priority == 3
        assert self.task.retry_count == 0

    def test_initial_status_pending(self):
        from core.loop_task import TaskStatus
        assert self.task.status == TaskStatus.PENDING

    def test_mark_running(self):
        from core.loop_task import TaskStatus
        self.task.mark_running()
        assert self.task.status == TaskStatus.RUNNING
        assert self.task.started_at is not None

    def test_mark_completed(self):
        from core.loop_task import TaskStatus
        self.task.mark_running()
        self.task.mark_completed("Post written successfully")
        assert self.task.status == TaskStatus.COMPLETED
        assert self.task.result_summary is not None
        assert self.task.execution_time is not None
        assert self.task.execution_time >= 0

    def test_mark_failed_increments_retry(self):
        from core.loop_task import TaskStatus
        self.task.mark_failed("LLM error")
        assert self.task.status == TaskStatus.FAILED
        assert self.task.retry_count == 1
        assert self.task.error is not None

    def test_is_retryable_when_under_max(self):
        self.task.mark_failed("error")
        assert self.task.is_retryable is True

    def test_not_retryable_when_at_max(self):
        self.task.mark_failed("error 1")
        self.task.status = __import__('core.loop_task',
                                       fromlist=['TaskStatus']).TaskStatus.FAILED
        self.task.mark_failed("error 2")
        assert self.task.is_retryable is False

    def test_mark_skipped(self):
        from core.loop_task import TaskStatus
        self.task.mark_skipped("circuit breaker open")
        assert self.task.status == TaskStatus.SKIPPED

    def test_to_dict_serializable(self):
        import json
        d = self.task.to_dict()
        json_str = json.dumps(d)
        assert self.task.task_id in json_str
        assert "status" in d

    def test_from_dict_roundtrip(self):
        from core.loop_task import LoopTask
        d = self.task.to_dict()
        restored = LoopTask.from_dict(d)
        assert restored.task_id == self.task.task_id
        assert restored.agent_id == self.task.agent_id
        assert restored.status == self.task.status

    def test_unique_task_ids(self):
        from core.loop_task import LoopTask
        ids = {LoopTask(agent_id="a", task="t").task_id for _ in range(50)}
        assert len(ids) == 50


# ─────────────────────────────────────────────
# AutonomousLoop tests
# ─────────────────────────────────────────────
class TestAutonomousLoop:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        from core.autonomous_loop import AutonomousLoop
        self.loop = AutonomousLoop()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_instantiation(self):
        assert self.loop is not None
        assert self.loop.queue_size() == 0
        assert not self.loop._running

    def test_enqueue_increases_queue(self):
        from core.loop_task import LoopTask
        task = LoopTask(agent_id="test", task="do something")
        self.loop.enqueue(task)
        assert self.loop.queue_size() == 1

    def test_enqueue_priority_ordering(self):
        from core.loop_task import LoopTask
        self.loop.enqueue(LoopTask(agent_id="a", task="low", priority=8))
        self.loop.enqueue(LoopTask(agent_id="b", task="high", priority=1))
        self.loop.enqueue(LoopTask(agent_id="c", task="mid", priority=5))
        assert self.loop._queue[0].priority == 1
        assert self.loop._queue[-1].priority == 8

    def test_dequeue_returns_task(self):
        from core.loop_task import LoopTask
        task = LoopTask(agent_id="test", task="do work")
        self.loop.enqueue(task)
        dequeued = self.loop.dequeue()
        assert dequeued is not None
        assert dequeued.task_id == task.task_id
        assert self.loop.queue_size() == 0

    def test_dequeue_skips_open_circuit(self):
        from core.loop_task import LoopTask, TaskStatus
        task = LoopTask(agent_id="broken_agent", task="will be skipped")
        cb = self.loop._get_circuit_breaker("broken_agent")
        for _ in range(5):
            cb._on_failure()
        assert cb.is_open
        self.loop.enqueue(task)
        result = self.loop.dequeue()
        assert result is None
        assert any(t.status == TaskStatus.SKIPPED for t in self.loop._failed)

    def test_enqueue_many(self):
        from core.loop_task import LoopTask
        tasks = [LoopTask(agent_id=f"agent_{i}", task=f"task {i}") for i in range(5)]
        self.loop.enqueue_many(tasks)
        assert self.loop.queue_size() == 5

    def test_get_status_structure(self):
        status = self.loop.get_status()
        assert "running" in status
        assert "queue_size" in status
        assert "completed" in status
        assert "failed" in status
        assert "circuit_breakers" in status

    def test_stop_sets_running_false(self):
        self.loop._running = True
        self.loop.stop()
        assert not self.loop._running

    @pytest.mark.asyncio
    async def test_run_empty_queue_completes(self):
        result = await self.loop.run(max_iterations=5)
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert result.data["iterations"] == 0

    @pytest.mark.asyncio
    async def test_run_with_mock_orchestrator(self):
        from core.loop_task import LoopTask

        mock_orchestrator = MagicMock()
        mock_orchestrator._call_agent = AsyncMock(return_value=TaskResult(
            success=True,
            data={"output": "task completed successfully"}
        ))
        self.loop.orchestrator = mock_orchestrator

        task = LoopTask(
            agent_id="test_agent",
            task="complete this task",
            use_evaluator=False
        )
        self.loop.enqueue(task)
        result = await self.loop.run(max_iterations=3, tick_interval=0.01)
        assert result.success is True
        assert result.data["completed"] >= 1

    @pytest.mark.asyncio
    async def test_run_handles_task_failure_with_retry(self):
        from core.loop_task import LoopTask

        call_count = 0
        async def failing_dispatch(agent_id, task, **kwargs):
            nonlocal call_count
            call_count += 1
            return TaskResult(success=False, error="simulated failure")

        mock_orchestrator = MagicMock()
        mock_orchestrator._call_agent = failing_dispatch
        self.loop.orchestrator = mock_orchestrator

        task = LoopTask(
            agent_id="flaky_agent",
            task="this will fail",
            max_retries=2,
            use_evaluator=False
        )
        self.loop.enqueue(task)
        result = await self.loop.run(max_iterations=10, tick_interval=0.01)
        assert result.success is True
        # Task was retried up to max_retries
        assert call_count <= 3

    @pytest.mark.asyncio
    async def test_persist_state(self, tmp_path):
        with patch('core.autonomous_loop.STATE_DIR', tmp_path), \
             patch('core.autonomous_loop.CHECKPOINT_FILE',
                   tmp_path / "checkpoints" / "loop_checkpoint.json"):
            (tmp_path / "checkpoints").mkdir(parents=True, exist_ok=True)
            (tmp_path / "queues").mkdir(exist_ok=True)
            await self.loop.persist_state()

    @pytest.mark.asyncio
    async def test_restore_state_no_checkpoint(self):
        with patch('core.autonomous_loop.CHECKPOINT_FILE',
                   __import__('pathlib').Path('/nonexistent/path.json')):
            result = await self.loop.restore_state()
        assert result is False

    def test_get_circuit_breaker_creates_per_agent(self):
        cb1 = self.loop._get_circuit_breaker("agent_a")
        cb2 = self.loop._get_circuit_breaker("agent_b")
        cb1_again = self.loop._get_circuit_breaker("agent_a")
        assert cb1 is not cb2
        assert cb1 is cb1_again  # same object

    @pytest.mark.asyncio
    async def test_health_check_doesnt_crash(self):
        try:
            await self.loop._health_check()
            assert True
        except Exception as e:
            pytest.fail(f"_health_check crashed: {e}")


# ─────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────
class TestSprintGIntegration:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_all_imports(self):
        from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        from core.loop_task import LoopTask, TaskStatus
        from core.autonomous_loop import AutonomousLoop
        assert all([CircuitBreaker, CircuitBreakerConfig, LoopTask,
                    TaskStatus, AutonomousLoop])

    def test_loop_task_status_enum_complete(self):
        from core.loop_task import TaskStatus
        statuses = [s.value for s in TaskStatus]
        for expected in ["pending", "running", "completed", "failed", "skipped"]:
            assert expected in statuses

    def test_circuit_breaker_used_by_loop(self):
        from core.autonomous_loop import AutonomousLoop
        from core.circuit_breaker import CircuitBreaker
        loop = AutonomousLoop()
        cb = loop._get_circuit_breaker("some_agent")
        assert isinstance(cb, CircuitBreaker)

    def test_observer_integration_in_loop(self):
        from core.autonomous_loop import AutonomousLoop
        from core.observability.observer import MoonObserver
        loop = AutonomousLoop()
        assert loop.observer is MoonObserver.get_instance()

    @pytest.mark.asyncio
    async def test_full_lifecycle_dry_run(self):
        """Full lifecycle: enqueue → run → complete → persist state."""
        from core.autonomous_loop import AutonomousLoop
        from core.loop_task import LoopTask

        loop = AutonomousLoop()
        mock_orch = MagicMock()
        mock_orch._call_agent = AsyncMock(return_value=TaskResult(
            success=True, data={"result": "done"}
        ))
        loop.orchestrator = mock_orch

        for i in range(3):
            loop.enqueue(LoopTask(
                agent_id="test_agent",
                task=f"task number {i}",
                use_evaluator=False,
                priority=i + 1
            ))

        result = await loop.run(max_iterations=5, tick_interval=0.01)
        assert result.success is True
        assert result.data["completed"] == 3

    def test_data_directories_created(self):
        from pathlib import Path
        assert Path("data/loop_state").exists()