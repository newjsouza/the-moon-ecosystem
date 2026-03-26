"""
tests/test_moon_sentinel.py
Unit tests for MoonSentinelAgent — the proactive autonomy engine.
"""
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import pytest

from agents.moon_sentinel import MoonSentinelAgent
from core.agent_base import TaskResult


# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def sentinel(tmp_path, monkeypatch):
    """MoonSentinelAgent with isolated file paths."""
    monkeypatch.setattr("agents.moon_sentinel.INITIATIVES_LOG", tmp_path / "initiatives.json")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    agent = MoonSentinelAgent(orchestrator=None)
    return agent


@pytest.fixture
def mock_orchestrator():
    orc = MagicMock()
    orc._agents = {}
    orc._circuits = {}
    return orc


# ─────────────────────────────────────────────────────────────
#  Tests: _execute (on-demand interface)
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_status(sentinel):
    result = await sentinel._execute("status")
    assert result.success
    assert result.data["agent"] == "MoonSentinelAgent"
    assert "initiatives_last_24h" in result.data


@pytest.mark.asyncio
async def test_execute_initiatives(sentinel):
    sentinel._log_initiative("test_key", "tech_trend", {"topics": ["AI"]})
    result = await sentinel._execute("initiatives")
    assert result.success
    assert len(result.data["initiatives"]) >= 1


@pytest.mark.asyncio
async def test_execute_unknown_action(sentinel):
    result = await sentinel._execute("unknown_action_xyz")
    assert result.success
    assert "Sentinel recebeu" in result.data["message"]


# ─────────────────────────────────────────────────────────────
#  Tests: Initiative Log
# ─────────────────────────────────────────────────────────────

def test_log_initiative_persists(sentinel, tmp_path):
    sentinel._log_initiative("key1", "tech_trend", {"topics": ["IA"]})
    assert len(sentinel._initiatives) == 1
    assert sentinel._initiatives[0]["key"] == "key1"
    assert sentinel._initiatives[0]["type"] == "tech_trend"


def test_was_initiative_done_today(sentinel):
    key = "morning_report_test"
    sentinel._log_initiative(key, "scheduled_report", {})
    # Key was just logged, so it must be found
    assert sentinel._was_initiative_done_today(key) is True
    assert sentinel._was_initiative_done_today("nonexistent_key_xyz") is False


def test_initiatives_capped_at_200(sentinel):
    for i in range(250):
        sentinel._log_initiative(f"key_{i}", "tech_trend", {})
    assert len(sentinel._initiatives) <= 200


# ─────────────────────────────────────────────────────────────
#  Tests: Ecosystem Health Watch
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watch_ecosystem_health_no_orchestrator(sentinel):
    result = await sentinel._watch_ecosystem_health()
    assert result["healthy_agents"] == 0
    assert result["issues"] == []
    assert "checked_at" in result


@pytest.mark.asyncio
async def test_watch_ecosystem_health_with_open_circuit(sentinel, mock_orchestrator):
    sentinel.orchestrator = mock_orchestrator
    bad_circuit = MagicMock()
    bad_circuit.open = True
    good_circuit = MagicMock()
    good_circuit.open = False
    mock_orchestrator._circuits = {
        "BadAgent": bad_circuit,
        "GoodAgent": good_circuit,
    }

    result = await sentinel._watch_ecosystem_health()
    assert len(result["issues"]) == 1
    assert "BadAgent" in result["issues"][0]
    assert result["healthy_agents"] == 1


# ─────────────────────────────────────────────────────────────
#  Tests: Tech Trends
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watch_tech_trends_no_llm_no_researcher(sentinel):
    """Without LLM or ResearcherAgent, should complete gracefully with empty findings."""
    report = await sentinel._watch_tech_trends()
    # Should return a string (either the no-findings message or a report)
    assert isinstance(report, str)


@pytest.mark.asyncio
async def test_llm_trend_synthesis_no_key(sentinel, monkeypatch):
    monkeypatch.setattr("agents.moon_sentinel.GROQ_API_KEY", "")
    findings = await sentinel._llm_trend_synthesis(["AI", "automation"])
    assert findings == []  # No GROQ_API_KEY


# ─────────────────────────────────────────────────────────────
#  Tests: Telegram Sender
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_telegram_no_config(sentinel, monkeypatch):
    """With no token/chat configured, send_telegram should return False silently."""
    monkeypatch.setattr("agents.moon_sentinel.TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr("agents.moon_sentinel.TELEGRAM_CHAT_ID", "")
    result = await sentinel._send_telegram("Hello")
    assert result is False


# ─────────────────────────────────────────────────────────────
#  Tests: On-skill-proposed handler
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_skill_proposed_logs_initiative(sentinel):
    await sentinel._on_skill_proposed({"skill": "test-lib", "path": "/path/to/skill"})
    assert any(
        i["type"] == "skill_discovery" and "test-lib" in i["key"]
        for i in sentinel._initiatives
    )


# ─────────────────────────────────────────────────────────────
#  Tests: Initiative Report
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_initiative_report_no_telegram(sentinel):
    """Report should generate without sending to Telegram when send_telegram=False."""
    report = await sentinel._generate_initiative_report(send_telegram=False)
    assert isinstance(report, str)
    assert "The Moon" in report


@pytest.mark.asyncio
async def test_generate_initiative_report_with_initiatives(sentinel):
    sentinel._log_initiative("tech_watch_1", "tech_trend", {"topics": ["AI"], "findings": 3})
    sentinel._log_initiative("skill_1", "skill_discovery", {"skill": "awesome-lib"})
    report = await sentinel._generate_initiative_report(send_telegram=False)
    assert isinstance(report, str)
    assert len(report) > 50
