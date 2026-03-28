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
from core.message_bus import Message


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


@pytest.mark.asyncio
async def test_execute_implement_research(sentinel):
    sentinel._implement_from_recent_research = AsyncMock(
        return_value={"overall_success": True, "actions_executed": []}
    )
    result = await sentinel._execute("implement-research")
    assert result.success is True
    assert result.data["implementation_report"]["overall_success"] is True


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


def test_validate_research_packets_rejects_placeholder_data(sentinel):
    packets = [
        {
            "topic": "agentic AI",
            "source_agent": "ResearcherAgent",
            "sources_used": ["web"],
            "total_results": 2,
            "synthesis": "Descobertas apontam oportunidade de melhorar autonomia e segurança do pipeline.",
            "references": [
                {"source": "web", "title": "Framework A", "url": "https://example.com/a"},
            ],
        }
    ]

    validation = sentinel._validate_research_packets(packets)
    assert validation["validated_packets_count"] == 0
    assert validation["rejected_packets_count"] == 1


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


@pytest.mark.asyncio
async def test_send_telegram_dedup_skips_duplicate_payload(sentinel, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    calls = {"count": 0}

    class DummyResp:
        status_code = 200

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            calls["count"] += 1
            return DummyResp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    first = await sentinel._send_telegram("Relatorio real", parse_mode=None, dedup_key="k1")
    second = await sentinel._send_telegram("Relatorio real", parse_mode=None, dedup_key="k1")

    assert first is True
    assert second is True
    assert calls["count"] == 1


def test_split_telegram_chunks_respects_size(sentinel):
    text = ("linha-1234567890\n" * 40).strip()
    chunks = sentinel._split_telegram_chunks(text, max_chars=80)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 80 for chunk in chunks)


@pytest.mark.asyncio
async def test_send_telegram_long_sends_multiple_chunks(sentinel):
    sentinel._send_telegram = AsyncMock(return_value=True)
    long_text = ("abcde\n" * 900).strip()

    delivered = await sentinel._send_telegram_long(long_text, parse_mode=None)

    assert delivered is True
    assert sentinel._send_telegram.await_count >= 2


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


@pytest.mark.asyncio
async def test_on_skill_proposed_accepts_message_object(sentinel):
    message = Message(
        sender="SkillAlchemist",
        topic="alchemist.skill_proposed",
        payload={"skill": "message-lib", "path": "/path/message"},
    )
    await sentinel._on_skill_proposed(message)
    assert any(
        i["type"] == "skill_discovery" and "message-lib" in i["key"]
        for i in sentinel._initiatives
    )


@pytest.mark.asyncio
async def test_on_devops_scan_accepts_message_object(sentinel):
    message = Message(
        sender="AutonomousDevOpsRefactor",
        topic="devops.scan_complete",
        payload={"summary": {"critical": 1, "high": 1, "medium": 0, "low": 0}},
    )
    await sentinel._on_devops_scan(message)
    assert any(i["type"] == "devops_scan" for i in sentinel._initiatives)


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


def test_format_detailed_trend_report_includes_evidence(sentinel):
    packets = [
        {
            "topic": "Agentes autônomos",
            "source_agent": "DeepWebResearchAgent",
            "sources_used": ["github", "arxiv"],
            "total_results": 7,
            "synthesis": "Foram encontrados frameworks promissores para autonomia.",
            "references": [
                {"source": "github", "title": "org/projeto-legal", "url": "https://github.com/org/projeto-legal"},
                {"source": "arxiv", "title": "Paper XYZ", "url": "https://arxiv.org/abs/0000.0000"},
            ],
        }
    ]

    detailed = sentinel._format_detailed_trend_report(packets)
    assert "RELATORIO DETALHADO DE PESQUISA" in detailed
    assert "Agentes autônomos" in detailed
    assert "https://github.com/org/projeto-legal" in detailed


@pytest.mark.asyncio
async def test_auto_implement_research_improvements_generates_report(sentinel, tmp_path, monkeypatch):
    impl_dir = tmp_path / "implementations"
    monkeypatch.setattr("agents.moon_sentinel.IMPLEMENTATION_REPORTS_DIR", impl_dir)

    orchestrator = MagicMock()
    orchestrator._call_agent = AsyncMock(return_value=TaskResult(success=True, data={"ok": True}))
    sentinel.orchestrator = orchestrator

    packets = [
        {
            "topic": "Segurança em agentes",
            "synthesis": "Há risco de vulnerabilidade e falhas de segurança.",
            "references": [{"source": "github", "title": "repo", "url": "https://github.com/example/repo"}],
            "sources_used": ["github"],
            "source_agent": "DeepWebResearchAgent",
            "total_results": 3,
        }
    ]

    report = await sentinel._auto_implement_research_improvements(
        detailed_packets=packets,
        summary_report="Resumo",
    )

    assert report is not None
    assert report["overall_success"] is True
    assert Path(report["report_file"]).exists()
    assert orchestrator._call_agent.await_count >= 3
