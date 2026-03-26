"""
Tests for RadarAgent: deduplication, state persistence, task routing.
"""
import asyncio
import os
import pytest
from unittest.mock import patch
from agents.radar_agent import RadarAgent
from skills.radar import RadarItem
from core.agent_base import TaskResult


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setattr("agents.radar_agent.STATE_FILE", str(tmp_path / "state.json"))
    return RadarAgent()


class TestDeduplication:
    def test_new_item_passes_filter(self, agent):
        items = [RadarItem("s", "t", "d", "http://a.com")]
        assert len(agent._filter_new(items)) == 1

    def test_seen_item_filtered(self, agent):
        items = [RadarItem("s", "t", "d", "http://a.com")]
        agent._mark_seen(items)
        assert agent._filter_new(items) == []

    def test_ring_buffer_max_size(self, agent):
        items = [RadarItem("s", f"t{i}", "d", f"http://{i}.com") for i in range(1100)]
        agent._mark_seen(items)
        assert len(agent._state["seen_hashes"]) <= 1000


class TestExecution:
    def test_execute_quick_pulse_returns_task_result(self, agent):
        async def run():
            empty = []
            with patch("agents.radar_agent.scan_github_trending", return_value=empty), \
                 patch("agents.radar_agent.scan_huggingface_models", return_value=empty), \
                 patch("agents.radar_agent.scan_huggingface_spaces", return_value=empty):
                return await agent._execute("quick_pulse")
        result = asyncio.run(run())
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert "new_items" in result.data

    def test_execute_error_returns_failed_result(self, agent):
        async def run():
            with patch("agents.radar_agent.scan_github_trending", side_effect=Exception("boom")):
                return await agent._execute("quick_pulse")
        result = asyncio.run(run())
        assert result.success is False
        assert result.error is not None

    def test_get_status(self, agent):
        status = agent.get_status()
        assert "seen_hashes_count" in status
        assert "last_scans" in status
