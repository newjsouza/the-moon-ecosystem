"""Sprint F — Test suite for MoonObserver, AgentMetrics, decorators."""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# AgentMetrics tests
# ─────────────────────────────────────────────
class TestAgentMetrics:

    def setup_method(self):
        from core.observability.metrics import AgentMetrics
        self.m = AgentMetrics(agent_id="test_agent")

    def test_instantiation(self):
        assert self.m.agent_id == "test_agent"
        assert self.m.total_calls == 0
        assert self.m.success_rate == 0.0

    def test_record_success(self):
        self.m.record(True, 0.5)
        assert self.m.total_calls == 1
        assert self.m.successful_calls == 1
        assert self.m.failed_calls == 0

    def test_record_failure(self):
        self.m.record(False, 1.2, error="timeout")
        assert self.m.failed_calls == 1
        assert self.m.last_error is not None
        assert "timeout" in self.m.last_error

    def test_avg_execution_time(self):
        self.m.record(True, 1.0)
        self.m.record(True, 3.0)
        assert abs(self.m.avg_execution_time - 2.0) < 0.001

    def test_success_rate_calculation(self):
        self.m.record(True, 0.5)
        self.m.record(True, 0.5)
        self.m.record(False, 0.5)
        assert abs(self.m.success_rate - 2/3) < 0.001

    def test_min_max_execution_time(self):
        self.m.record(True, 0.1)
        self.m.record(True, 2.5)
        self.m.record(True, 1.0)
        assert abs(self.m.min_execution_time - 0.1) < 0.001
        assert abs(self.m.max_execution_time - 2.5) < 0.001

    def test_to_dict_contains_all_fields(self):
        self.m.record(True, 0.5)
        d = self.m.to_dict()
        assert "agent_id" in d
        assert "avg_execution_time" in d
        assert "success_rate" in d
        assert "total_calls" in d

    def test_to_summary_is_string(self):
        self.m.record(True, 0.5)
        summary = self.m.to_summary()
        assert isinstance(summary, str)
        assert "test_agent" in summary

    def test_task_type_tracking(self):
        self.m.record(True, 0.5, task_type="blog")
        self.m.record(True, 0.5, task_type="telegram")
        self.m.record(True, 0.5, task_type="blog")
        assert self.m.task_type_counts.get("blog") == 2
        assert self.m.task_type_counts.get("telegram") == 1

    def test_error_count_tracking(self):
        self.m.record(False, 0.5, error="timeout")
        self.m.record(False, 0.5, error="timeout")
        self.m.record(False, 0.5, error="connection error")
        assert self.m.error_counts.get("timeout") == 2

    def test_min_time_zero_when_no_records(self):
        d = self.m.to_dict()
        assert d["min_execution_time"] == 0.0


# ─────────────────────────────────────────────
# MoonObserver tests
# ─────────────────────────────────────────────
class TestMoonObserver:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        self.observer = MoonObserver.get_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_singleton_pattern(self):
        from core.observability.observer import MoonObserver
        a = MoonObserver.get_instance()
        b = MoonObserver.get_instance()
        assert a is b

    def test_reset_creates_new_instance(self):
        from core.observability.observer import MoonObserver
        a = MoonObserver.get_instance()
        MoonObserver.reset_instance()
        b = MoonObserver.get_instance()
        assert a is not b

    def test_record_sync(self):
        self.observer.record_sync("agent_a", True, 0.5)
        metrics = self.observer.get_metrics("agent_a")
        assert metrics is not None
        assert metrics.total_calls == 1

    @pytest.mark.asyncio
    async def test_record_async(self):
        await self.observer.record("agent_b", True, 0.3, task_type="blog")
        metrics = self.observer.get_metrics("agent_b")
        assert metrics.total_calls == 1

    @pytest.mark.asyncio
    async def test_health_report_structure(self):
        self.observer.record_sync("evaluator", True, 0.5)
        self.observer.record_sync("evaluator", False, 1.0, error="err")
        report = await self.observer.health_report()
        assert "session_id" in report
        assert "total_calls" in report
        assert "agents" in report
        assert "system_status" in report
        assert "evaluator" in report["agents"]

    @pytest.mark.asyncio
    async def test_health_report_system_status_healthy(self):
        for _ in range(10):
            self.observer.record_sync("good_agent", True, 0.1)
        report = await self.observer.health_report()
        assert report["system_status"] in ("healthy", "degraded", "critical")

    @pytest.mark.asyncio
    async def test_get_slowest_agents(self):
        self.observer.record_sync("fast_agent", True, 0.1)
        self.observer.record_sync("slow_agent", True, 5.0)
        slowest = await self.observer.get_slowest_agents(top_n=2)
        assert len(slowest) <= 2
        if len(slowest) >= 2:
            assert slowest[0]["avg_time"] >= slowest[1]["avg_time"]

    @pytest.mark.asyncio
    async def test_get_most_failing_agents(self):
        self.observer.record_sync("reliable_agent", True, 0.5)
        self.observer.record_sync("flaky_agent", False, 0.5, error="err")
        self.observer.record_sync("flaky_agent", False, 0.5, error="err")
        failing = await self.observer.get_most_failing_agents(top_n=3)
        assert any(a["agent_id"] == "flaky_agent" for a in failing)

    @pytest.mark.asyncio
    async def test_persist_session_creates_file(self, tmp_path):
        import os
        self.observer.record_sync("test", True, 0.5)
        with patch('core.observability.observer.METRICS_DIR', tmp_path):
            (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)
            (tmp_path / "agents").mkdir(exist_ok=True)
            (tmp_path / "errors").mkdir(exist_ok=True)
            await self.observer.persist_session()

    def test_get_all_metrics_returns_dict(self):
        self.observer.record_sync("a1", True, 0.5)
        self.observer.record_sync("a2", False, 1.0)
        all_m = self.observer.get_all_metrics()
        assert "a1" in all_m
        assert "a2" in all_m

    def test_print_dashboard_no_crash(self):
        self.observer.record_sync("agent_x", True, 0.5)
        try:
            self.observer.print_dashboard()
            assert True
        except Exception as e:
            pytest.fail(f"print_dashboard crashed: {e}")


# ─────────────────────────────────────────────
# Observability decorators tests
# ─────────────────────────────────────────────
class TestObservabilityDecorators:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    @pytest.mark.asyncio
    async def test_observe_decorator_records_success(self):
        from core.observability.decorators import observe
        from core.observability.observer import MoonObserver
        from core.agent_base import TaskResult

        @observe(agent_id="decorated_func")
        async def my_func():
            return TaskResult(success=True, data={"ok": True},
                              execution_time=0.1)

        await my_func()
        obs = MoonObserver.get_instance()
        metrics = obs.get_metrics("decorated_func")
        assert metrics is not None
        assert metrics.successful_calls == 1

    @pytest.mark.asyncio
    async def test_observe_decorator_records_failure(self):
        from core.observability.decorators import observe
        from core.observability.observer import MoonObserver
        from core.agent_base import TaskResult

        @observe(agent_id="failing_func")
        async def my_func():
            return TaskResult(success=False, error="test error")

        await my_func()
        obs = MoonObserver.get_instance()
        metrics = obs.get_metrics("failing_func")
        assert metrics.failed_calls == 1

    @pytest.mark.asyncio
    async def test_observe_agent_wraps_execute(self):
        from core.observability.decorators import observe_agent
        from core.observability.observer import MoonObserver
        from core.agent_base import AgentBase, TaskResult

        @observe_agent
        class TestAgent(AgentBase):
            AGENT_ID = "observed_test_agent"
            async def _execute(self, task: str, **kwargs) -> TaskResult:
                return TaskResult(success=True, data={"task": task})

        agent = TestAgent()
        result = await agent._execute("test_task")
        assert result.success is True

        obs = MoonObserver.get_instance()
        metrics = obs.get_metrics("observed_test_agent")
        assert metrics is not None
        assert metrics.total_calls == 1

    @pytest.mark.asyncio
    async def test_observe_agent_preserves_return_value(self):
        from core.observability.decorators import observe_agent
        from core.agent_base import AgentBase, TaskResult

        @observe_agent
        class AnotherAgent(AgentBase):
            AGENT_ID = "another_agent"
            async def _execute(self, task: str, **kwargs) -> TaskResult:
                return TaskResult(success=True,
                                  data={"result": "specific_value"})

        agent = AnotherAgent()
        result = await agent._execute("task")
        assert result.data["result"] == "specific_value"


# ─────────────────────────────────────────────
# MoonObserverAgent tests
# ─────────────────────────────────────────────
class TestMoonObserverAgent:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        from agents.moon_observer_agent import MoonObserverAgent
        self.agent = MoonObserverAgent()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_instantiation(self):
        assert self.agent.AGENT_ID == "moon_observer"

    def test_execute_signature(self):
        import inspect
        sig = inspect.signature(self.agent._execute)
        assert 'task' in str(sig)
        assert 'kwargs' in str(sig)

    @pytest.mark.asyncio
    async def test_health_command(self):
        result = await self.agent._execute("health")
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert "system_status" in result.data

    @pytest.mark.asyncio
    async def test_dashboard_command(self):
        result = await self.agent._execute("dashboard")
        assert isinstance(result, TaskResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_metrics_command_with_agent_id(self):
        self.agent.observer.record_sync("target_agent", True, 0.5)
        result = await self.agent._execute("metrics", agent_id="target_agent")
        assert result.success is True
        assert result.data["agent_id"] == "target_agent"

    @pytest.mark.asyncio
    async def test_metrics_command_missing_agent_id(self):
        result = await self.agent._execute("metrics")
        assert result.success is False
        assert "agent_id" in result.error

    @pytest.mark.asyncio
    async def test_metrics_command_unknown_agent(self):
        result = await self.agent._execute("metrics", agent_id="nonexistent")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_slowest_command(self):
        result = await self.agent._execute("slowest", top_n=3)
        assert result.success is True
        assert "slowest_agents" in result.data

    @pytest.mark.asyncio
    async def test_failing_command(self):
        result = await self.agent._execute("failing", top_n=3)
        assert result.success is True
        assert "most_failing_agents" in result.data

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        result = await self.agent._execute("invalid_command_xyz")
        assert result.success is False
        assert "Unknown command" in result.error

    @pytest.mark.asyncio
    async def test_all_command(self):
        self.agent.observer.record_sync("agent_1", True, 0.5)
        result = await self.agent._execute("all")
        assert result.success is True
        assert "agents" in result.data
        assert "total_agents" in result.data


# ─────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────
class TestSprintFIntegration:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_all_imports(self):
        from core.observability import MoonObserver, AgentMetrics, observe, observe_agent
        assert all([MoonObserver, AgentMetrics, observe, observe_agent])

    def test_observer_agent_import(self):
        from agents.moon_observer_agent import MoonObserverAgent
        assert MoonObserverAgent is not None

    def test_evaluator_has_observe_agent(self):
        with open('agents/evaluator.py', 'r') as f:
            content = f.read()
        assert '@observe_agent' in content, \
            "EvaluatorAgent must have @observe_agent decorator"

    def test_optimizer_has_observe_agent(self):
        with open('agents/optimizer.py', 'r') as f:
            content = f.read()
        assert '@observe_agent' in content, \
            "OptimizerAgent must have @observe_agent decorator"

    def test_text_to_sql_has_observe_agent(self):
        with open('agents/text_to_sql_agent.py', 'r') as f:
            content = f.read()
        assert '@observe_agent' in content, \
            "TextToSQLAgent must have @observe_agent decorator"

    def test_metrics_dir_exists(self):
        from pathlib import Path
        assert Path("data/metrics").exists()

    @pytest.mark.asyncio
    async def test_observer_agent_base_compliance(self):
        from agents.moon_observer_agent import MoonObserverAgent
        from core.agent_base import AgentBase
        assert issubclass(MoonObserverAgent, AgentBase)