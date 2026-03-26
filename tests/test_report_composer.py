"""
Tests for ReportComposerAgent.
"""
import asyncio
import pytest
from agents.report_composer import ReportComposerAgent
from core.agent_base import TaskResult

_MOCK_DATA = {
    "new_items": [
        {"source": "github_trending", "title": "owner/repo", "description": "A tool",
         "url": "https://github.com/owner/repo", "category": "code_repository", "item_hash": "abc", "timestamp": ""},
        {"source": "huggingface_models", "title": "vendor/model", "description": "text-gen",
         "url": "https://huggingface.co/vendor/model", "category": "llm_model", "item_hash": "def", "timestamp": ""},
    ],
    "total_new": 2, "total_scanned": 100,
}


class MockLLM:
    async def complete(self, *a, **kw):
        return "🌙 *The Moon — Radar Inteligente*\n_01/01 UTC_\n\nConteúdo suficientemente longo para passar na validação de 80 caracteres do sistema."


class FailingLLM:
    async def complete(self, *a, **kw):
        raise Exception("LLM unavailable")


class TestReportComposer:
    def test_returns_task_result(self):
        agent = ReportComposerAgent(llm=MockLLM())
        result = asyncio.run(agent._execute("compose", radar_data=_MOCK_DATA))
        assert isinstance(result, TaskResult)
        assert result.success is True

    def test_report_has_content(self):
        agent = ReportComposerAgent(llm=MockLLM())
        result = asyncio.run(agent._execute("compose", radar_data=_MOCK_DATA))
        assert len(result.data.get("report", "")) > 50

    def test_empty_scan_shows_sleep_emoji(self):
        agent = ReportComposerAgent()
        result = asyncio.run(agent._execute(
            "compose",
            radar_data={"new_items": [], "total_new": 0, "total_scanned": 50}
        ))
        assert result.success is True
        assert "💤" in result.data.get("report", "")

    def test_fallback_when_llm_fails(self):
        agent = ReportComposerAgent(llm=FailingLLM())
        result = asyncio.run(agent._execute("compose", radar_data=_MOCK_DATA))
        assert result.success is True
        assert len(result.data.get("report", "")) > 30
