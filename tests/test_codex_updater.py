"""Tests for CodexUpdaterAgent."""
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from core.agent_base import TaskResult


class TestCodexUpdaterAgent:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_import(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        assert agent.AGENT_ID == "codex_updater"

    def test_subscribe_topics(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        assert "codex.update" in agent.SUBSCRIBE_TOPICS
        assert "autonomous_loop.task_completed" in agent.SUBSCRIBE_TOPICS

    def test_verify_codex_exists(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        result = agent._verify_codex()
        assert result["exists"] is True
        assert result["size_kb"] > 0

    def test_format_entry(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        entry = agent._format_entry(
            entry_type="feat",
            title="Test Feature",
            agent_id="blog_pipeline",
            summary="- Criado: `blog/pipeline.py`",
            timestamp="2026-03-21 10:00"
        )
        assert "feat".upper() in entry
        assert "Test Feature" in entry
        assert "blog_pipeline" in entry
        assert "2026-03-21" in entry

    def test_rule_based_summary(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        summary = agent._rule_based_summary(
            entry_type="feat",
            agent_id="sports_analytics",
            details={"files_created": ["agents/sports_analytics_agent.py"],
                     "tests_added": 25}
        )
        assert "sports_analytics" in summary
        assert "sports_analytics_agent.py" in summary
        assert "25" in summary

    @pytest.mark.asyncio
    async def test_atomic_append(self):
        from agents.codex_updater import CodexUpdaterAgent, CODEX_PATH
        agent = CodexUpdaterAgent()
        original = CODEX_PATH.read_text(encoding="utf-8")
        test_entry = "\n### TEST ENTRY — DELETAR\n\n- teste unitário\n\n---\n"
        await agent._atomic_append(test_entry)
        updated = CODEX_PATH.read_text(encoding="utf-8")
        assert "TEST ENTRY" in updated
        # cleanup
        CODEX_PATH.write_text(original, encoding="utf-8")

    @pytest.mark.asyncio
    async def test_execute_verify(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        result = await agent._execute("verify")
        assert result.success is True
        assert result.data["exists"] is True

    @pytest.mark.asyncio
    async def test_execute_status(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        result = await agent._execute("status")
        assert result.success is True
        assert isinstance(result.data["recent_entries"], list)

    @pytest.mark.asyncio
    async def test_execute_update(self):
        from agents.codex_updater import CodexUpdaterAgent, CODEX_PATH
        agent = CodexUpdaterAgent()
        original = CODEX_PATH.read_text(encoding="utf-8")
        with patch.object(agent.llm, 'complete',
                          new_callable=AsyncMock,
                          return_value="- Teste de update automático"):
            result = await agent._execute(
                "update",
                title="Sprint Test Smoke",
                agent_id="codex_updater",
                type="test",
                details={"files_created": ["tests/test_smoke.py"],
                         "tests_added": 1}
            )
        assert result.success is True
        # cleanup
        CODEX_PATH.write_text(original, encoding="utf-8")

    @pytest.mark.asyncio
    async def test_on_event_skips_empty_title(self):
        from agents.codex_updater import CodexUpdaterAgent
        from core.message_bus import Message
        agent = CodexUpdaterAgent()
        append_called = False
        async def mock_append(*a, **kw):
            nonlocal append_called
            append_called = True
        agent._append_entry = mock_append
        # Create a mock message with empty title
        msg = Message(sender="test", topic="codex.update", payload={"type": "feat"})
        await agent._on_event(msg)
        assert not append_called

    @pytest.mark.asyncio
    async def test_execute_unknown_command(self):
        from agents.codex_updater import CodexUpdaterAgent
        agent = CodexUpdaterAgent()
        result = await agent._execute("invalid_cmd")
        assert result.success is False
        assert "Unknown command" in result.error
