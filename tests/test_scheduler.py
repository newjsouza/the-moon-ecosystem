"""
Tests for MoonScheduler.
"""
import asyncio
import pytest
from core.scheduler import MoonScheduler
from core.agent_base import TaskResult


class MockRadar:
    async def execute(self, task, **kw):
        return TaskResult(success=True, data={"new_items": [], "total_new": 0, "total_scanned": 5})


class MockComposer:
    async def execute(self, task, **kw):
        return TaskResult(success=True, data={"report": "test report", "total_new": 0})


class FailRadar:
    async def execute(self, task, **kw):
        return TaskResult(success=False, error="scan failed")


class TestMoonScheduler:
    def test_status_before_start(self):
        s = MoonScheduler(MockRadar(), MockComposer())
        status = s.get_status()
        assert status["running"] is False
        assert "jobs" in status

    def test_stop_before_start_safe(self):
        s = MoonScheduler(MockRadar(), MockComposer())
        s.stop()

    def test_run_pipeline_success(self):
        sent = []

        async def sender(msg):
            sent.append(msg)

        result = asyncio.run(
            MoonScheduler(MockRadar(), MockComposer(), telegram_sender=sender).run_pipeline("quick_pulse")
        )
        assert result is True

    def test_run_pipeline_radar_failure(self):
        result = asyncio.run(
            MoonScheduler(FailRadar(), MockComposer()).run_pipeline("quick_pulse")
        )
        assert result is False
