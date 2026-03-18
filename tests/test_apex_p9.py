"""Testes P9 — generate_pre45_analysis com lineups reais do WebMCP."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


BASE_ANALYSIS = {
    "match_id": 999,
    "home_team": "Flamengo",
    "away_team": "Palmeiras",
    "competition": "Brasileirão",
    "kickoff_utc": "2026-03-17T21:00:00+00:00",
    "general_analysis": "Flamengo favorito em casa. Palmeiras defensivo.",
    "betting_markets": [],
}

WEBMCP_LINEUPS_FULL = {
    "home_lineup": [
        "Rossi", "Varela", "Léo Ortiz", "Léo Pereira", "Ayrton",
        "Evertton", "Gerson", "De la Cruz", "Arrascaeta", "Michael", "Pedro",
    ],
    "away_lineup": [
        "Weverton", "Marcos Rocha", "Gustavo Gómez", "Murilo", "Caio Paulista",
        "Aníbal", "Zé Rafael", "Raphael Veiga", "Dudu", "Rony", "Flaco López",
    ],
    "home_absent": [],
    "away_absent": ["Dudu"],
    "home_suspended": [],
    "away_suspended": [],
    "home_returns": [],
    "away_returns": ["Rony"],
    "source": "sofascore_api",
}

WEBMCP_LINEUPS_EMPTY = {
    "home_lineup": [],
    "away_lineup": [],
    "home_absent": [],
    "away_absent": [],
    "home_suspended": [],
    "away_suspended": [],
    "home_returns": [],
    "away_returns": [],
    "source": "sofascore_api",
}

WEBMCP_LINEUPS_NEWS = {
    "home_lineup": [],
    "away_lineup": [],
    "home_absent": [],
    "away_absent": [],
    "home_suspended": [],
    "away_suspended": [],
    "home_returns": [],
    "away_returns": [],
    "source": "news_sites",
    "news_articles": [
        {"title": "Flamengo confirma escalação", "url": "...", "source": "GloboEsporte"}
    ],
}


def _make_engine():
    from agents.apex.oracle import AnalysisEngine

    engine = AnalysisEngine.__new__(AnalysisEngine)
    engine.llm = MagicMock()
    engine.llm.generate = AsyncMock(
        return_value="Refinamento LLM com titulares confirmados."
    )
    return engine


@pytest.mark.asyncio
async def test_generate_pre45_accepts_no_webmcp_param():
    engine = _make_engine()
    result = await engine.generate_pre45_analysis(BASE_ANALYSIS.copy(), None)
    assert "analysis" in result
    assert "lineups" in result


@pytest.mark.asyncio
async def test_generate_pre45_accepts_webmcp_lineups():
    engine = _make_engine()
    result = await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    assert "analysis" in result
    assert "lineups" in result


@pytest.mark.asyncio
async def test_webmcp_lineups_merged_when_api_empty():
    engine = _make_engine()
    result = await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    assert result["lineups"]["home_lineup"] == WEBMCP_LINEUPS_FULL["home_lineup"]
    assert result["lineups"]["away_lineup"] == WEBMCP_LINEUPS_FULL["away_lineup"]


@pytest.mark.asyncio
async def test_webmcp_empty_lineups_keeps_warning():
    engine = _make_engine()
    result = await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_EMPTY
    )
    assert "⚠️" in result["analysis"]["refined_analysis"]


@pytest.mark.asyncio
async def test_news_only_keeps_warning():
    engine = _make_engine()
    result = await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_NEWS
    )
    assert "⚠️" in result["analysis"]["refined_analysis"]


@pytest.mark.asyncio
async def test_no_webmcp_no_api_keeps_warning():
    engine = _make_engine()
    result = await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=None
    )
    assert "⚠️" in result["analysis"]["refined_analysis"]


@pytest.mark.asyncio
async def test_llm_called_when_lineups_available():
    engine = _make_engine()
    await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    engine.llm.generate.assert_called_once()


@pytest.mark.asyncio
async def test_llm_prompt_contains_home_starters():
    engine = _make_engine()
    await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    prompt = engine.llm.generate.call_args.args[0]
    assert "Rossi" in prompt or "Pedro" in prompt or "Flamengo TITULARES" in prompt


@pytest.mark.asyncio
async def test_llm_prompt_contains_away_starters():
    engine = _make_engine()
    await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    prompt = engine.llm.generate.call_args.args[0]
    assert "Weverton" in prompt or "Flaco" in prompt or "Palmeiras TITULARES" in prompt


@pytest.mark.asyncio
async def test_llm_prompt_contains_absent_player():
    engine = _make_engine()
    await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    prompt = engine.llm.generate.call_args.args[0]
    assert "Dudu" in prompt


@pytest.mark.asyncio
async def test_llm_prompt_contains_source():
    engine = _make_engine()
    await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    prompt = engine.llm.generate.call_args.args[0]
    assert "sofascore_api" in prompt


@pytest.mark.asyncio
async def test_refined_analysis_uses_llm_output():
    engine = _make_engine()
    engine.llm.generate = AsyncMock(
        return_value="Flamengo confirmado com Pedro e Arrascaeta. Palmeiras sem Dudu."
    )
    result = await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    assert "Pedro" in result["analysis"]["refined_analysis"]
    assert "Dudu" in result["analysis"]["refined_analysis"]


@pytest.mark.asyncio
async def test_refined_analysis_fallback_on_llm_none():
    engine = _make_engine()
    engine.llm.generate = AsyncMock(return_value=None)
    analysis = BASE_ANALYSIS.copy()
    result = await engine.generate_pre45_analysis(
        analysis, None, webmcp_lineups=WEBMCP_LINEUPS_FULL
    )
    assert result["analysis"]["refined_analysis"] == analysis["general_analysis"]


@pytest.mark.asyncio
async def test_llm_not_called_when_no_lineups():
    engine = _make_engine()
    await engine.generate_pre45_analysis(
        BASE_ANALYSIS.copy(), None, webmcp_lineups=WEBMCP_LINEUPS_EMPTY
    )
    engine.llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_check_pre45_passes_webmcp_before_llm():
    from agents.apex.oracle import ApexOracle

    oracle = ApexOracle.__new__(ApexOracle)
    oracle.football = MagicMock()
    oracle.football.get_match_detail = AsyncMock(return_value=None)
    oracle.telegram = MagicMock()
    oracle.telegram.send = AsyncMock(return_value=True)
    oracle.formatter = MagicMock()
    oracle.formatter.format_pre45_analysis = MagicMock(return_value="msg")

    kickoff = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
    oracle.context = MagicMock()
    oracle.context.get_pending_pre45 = MagicMock(return_value=[{
        "match_id": 999,
        "home_team": "Flamengo",
        "away_team": "Palmeiras",
        "competition": "Brasileirão",
        "kickoff_utc": kickoff,
    }])
    oracle.context.mark_pre45_sent = MagicMock()

    oracle.engine = MagicMock()
    oracle.engine.generate_pre45_analysis = AsyncMock(return_value={
        "analysis": {"refined_analysis": "ok"},
        "lineups": WEBMCP_LINEUPS_FULL,
    })

    with patch(
        "agents.apex.oracle._fetch_webmcp_lineups",
        new_callable=AsyncMock,
        return_value=WEBMCP_LINEUPS_FULL,
    ) as mock_fetch:
        await oracle.check_pre45()

    mock_fetch.assert_called_once_with("Flamengo", "Palmeiras", "Brasileirão")
    assert (
        oracle.engine.generate_pre45_analysis.call_args.kwargs["webmcp_lineups"]
        == WEBMCP_LINEUPS_FULL
    )
