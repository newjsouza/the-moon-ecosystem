"""Testes unitários — WebMCP Sports Layer. Mock total, sem I/O real."""
import dataclasses
import pytest
from unittest.mock import AsyncMock, patch

from skills.webmcp.sports.schemas import (
    MatchInfo, Lineup, LineupPlayer, NewsArticle, SportsQueryResult,
)
from skills.webmcp.sports.sofascore import SofaScoreScraper
from skills.webmcp.sports.flashscore import FlashscoreScraper
from skills.webmcp.sports.news import SportsNewsScraper, is_lineup_news
from skills.webmcp.sports.lineup_detector import LineupDetector
from skills.webmcp.router import route, _is_sports
from agents.webmcp_agent import WebMCPAgent


# ── Fixtures ──────────────────────────────────────────────────

_PLAYER = LineupPlayer("Gerson", "MID", 8, True, True)
_LINEUP = Lineup("Flamengo", [_PLAYER], "4-3-3", confirmed=True, source="sofascore")
_MATCH = MatchInfo(
    match_id="999", home_team="Flamengo", away_team="Palmeiras",
    competition="Brasileirão", kickoff_utc="2026-03-17T21:00:00+00:00",
    home_lineup=_LINEUP, away_lineup=_LINEUP, source="sofascore",
)
_RESULT = SportsQueryResult(
    query="Flamengo vs Palmeiras", provider="sofascore",
    matches=[_MATCH], scraped_at="2026-03-17T00:00:00Z",
)
_NEWS_RESULT = SportsQueryResult(
    query="escalação Flamengo", provider="sports_news",
    news=[NewsArticle(
        title="Flamengo confirma escalação",
        url="https://ge.globo.com/flamengo",
        source="GloboEsporte", mentions_lineup=True,
        teams_mentioned=["Flamengo"],
    )],
)


# ── schemas ───────────────────────────────────────────────────

def test_lineup_starters():
    l = Lineup("X", [
        LineupPlayer("A", is_starter=True),
        LineupPlayer("B", is_starter=False),
    ])
    assert len(l.starters) == 1
    assert len(l.bench) == 1

def test_match_minutes_none_without_kickoff():
    m = MatchInfo(match_id="1", home_team="A", away_team="B")
    assert m.minutes_to_kickoff is None

def test_lineup_window_active_true():
    from datetime import datetime, timezone, timedelta
    ko = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
    m = MatchInfo(match_id="1", home_team="A", away_team="B", kickoff_utc=ko)
    assert m.lineup_window_active is True

def test_lineup_window_active_false_early():
    from datetime import datetime, timezone, timedelta
    ko = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    m = MatchInfo(match_id="1", home_team="A", away_team="B", kickoff_utc=ko)
    assert m.lineup_window_active is False

def test_sports_query_result_defaults():
    r = SportsQueryResult(query="q", provider="p")
    assert r.success is True
    assert r.matches == []
    assert r.news == []


# ── news detection ────────────────────────────────────────────

def test_is_lineup_news_escalacao():
    assert is_lineup_news("Escalação confirmada do Flamengo") is True

def test_is_lineup_news_titulares():
    assert is_lineup_news("Conheça os titulares do Palmeiras") is True

def test_is_lineup_news_negative():
    assert is_lineup_news("Mercado: atacante pode sair em junho") is False

def test_is_lineup_news_in_summary():
    assert is_lineup_news("Notícia", "time confirmado para a partida") is True


# ── router ────────────────────────────────────────────────────

def test_is_sports_positive():
    assert _is_sports("escalação do Flamengo hoje") is True
    assert _is_sports("resultado brasileirão") is True
    assert _is_sports("placar ao vivo") is True

def test_is_sports_negative():
    assert _is_sports("preço do bitcoin") is False
    assert _is_sports("tutorial python asyncio") is False

@pytest.mark.asyncio
async def test_route_sports_today():
    with patch.object(SofaScoreScraper, "get_today_matches",
                      new_callable=AsyncMock, return_value=_RESULT):
        r = await route("sports:today")
    assert "matches" in r

@pytest.mark.asyncio
async def test_route_sports_live():
    with patch.object(FlashscoreScraper, "get_live_matches",
                      new_callable=AsyncMock, return_value=_RESULT):
        r = await route("sports:live")
    assert "provider" in r

@pytest.mark.asyncio
async def test_route_sports_news():
    with patch.object(SportsNewsScraper, "get_latest_sports_news",
                      new_callable=AsyncMock, return_value=_NEWS_RESULT):
        r = await route("sports:news:futebol")
    assert "news" in r

@pytest.mark.asyncio
async def test_route_sports_lineup():
    with patch.object(LineupDetector, "detect_lineups",
                      new_callable=AsyncMock, return_value=_RESULT):
        r = await route("sports:lineup:Flamengo vs Palmeiras")
    assert "matches" in r

@pytest.mark.asyncio
async def test_route_generic_sports_text():
    with patch.object(SofaScoreScraper, "search_matches",
                      new_callable=AsyncMock, return_value=_RESULT):
        r = await route("sports:Flamengo Palmeiras")
    assert "provider" in r

@pytest.mark.asyncio
async def test_route_non_sports_delegates():
    r = await route("preço do dólar hoje")
    assert "__delegate__" in r


# ── WebMCPAgent ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_sports_prefix():
    agent = WebMCPAgent()
    with patch("skills.webmcp.router.route", new_callable=AsyncMock,
               return_value=dataclasses.asdict(_RESULT)):
        result = await agent._execute("sports:Flamengo")
    assert result.success is True

@pytest.mark.asyncio
async def test_agent_auto_detect_sports():
    agent = WebMCPAgent()
    with patch("skills.webmcp.router.route", new_callable=AsyncMock,
               return_value=dataclasses.asdict(_NEWS_RESULT)):
        result = await agent._execute("escalação do Flamengo hoje")
    assert result.success is True

@pytest.mark.asyncio
async def test_agent_lineup_returns_match_data():
    agent = WebMCPAgent()
    with patch("skills.webmcp.router.route", new_callable=AsyncMock,
               return_value=dataclasses.asdict(_RESULT)):
        result = await agent._execute("sports:lineup:Flamengo vs Palmeiras")
    assert result.success is True
    assert result.data["matches"][0]["home_team"] == "Flamengo"

@pytest.mark.asyncio
async def test_agent_error_returns_taskresult_failed():
    agent = WebMCPAgent()
    with patch("skills.webmcp.router.route", new_callable=AsyncMock,
               side_effect=Exception("timeout")):
        result = await agent._execute("sports:today")
    assert result.success is False
    assert "timeout" in result.error

@pytest.mark.asyncio
async def test_agent_execution_time_populated():
    agent = WebMCPAgent()
    with patch("skills.webmcp.router.route", new_callable=AsyncMock,
               return_value={"provider": "test", "matches": []}):
        result = await agent._execute("sports:hoje")
    assert result.execution_time >= 0.0
