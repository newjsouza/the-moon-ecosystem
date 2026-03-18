"""Testes unitários do APEXLineupPoller e do fallback WebMCP do Oracle."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.apex.lineup_poller import APEXLineupPoller
from agents.apex.oracle import _fetch_webmcp_lineups
from skills.webmcp.sports.schemas import (
    Lineup,
    LineupPlayer,
    MatchInfo,
    NewsArticle,
    SportsQueryResult,
)


def _make_context(matches: list) -> MagicMock:
    ctx = MagicMock()
    ctx._context = {"analyses": matches, "lineups_confirmed": {}}
    ctx._save = MagicMock()
    return ctx


def _make_telegram() -> AsyncMock:
    telegram = AsyncMock()
    telegram.send = AsyncMock(return_value=True)
    return telegram


def _match_dict(home: str, away: str, mins_ahead: float) -> dict:
    kickoff = (datetime.now(timezone.utc) + timedelta(minutes=mins_ahead)).isoformat()
    return {
        "match_id": abs(hash((home, away, mins_ahead))) % 100000,
        "home_team": home,
        "away_team": away,
        "competition": "Brasileirão",
        "kickoff_utc": kickoff,
    }


_PLAYER = LineupPlayer("Gerson", "MID", 8, True, True)
_HOME_LINEUP = Lineup(
    "Flamengo",
    [_PLAYER, LineupPlayer("Pedro", "FWD", 9, True, False)],
    "4-3-3",
    confirmed=True,
    source="sofascore",
)
_AWAY_LINEUP = Lineup(
    "Palmeiras",
    [LineupPlayer("Weverton", "GK", 21, True, True)],
    "4-4-2",
    confirmed=True,
    source="sofascore",
)
_MATCH_WITH_LINEUPS = MatchInfo(
    match_id="999",
    home_team="Flamengo",
    away_team="Palmeiras",
    competition="Brasileirão",
    home_lineup=_HOME_LINEUP,
    away_lineup=_AWAY_LINEUP,
    source="sofascore",
)
_RESULT_WITH_LINEUPS = SportsQueryResult(
    query="Flamengo vs Palmeiras",
    provider="sofascore",
    matches=[_MATCH_WITH_LINEUPS],
    raw_data={"lineup_source": "sofascore_api"},
)
_NEWS_RESULT = SportsQueryResult(
    query="Flamengo vs Palmeiras",
    provider="sports_news",
    news=[
        NewsArticle(
            title="Flamengo confirma escalação",
            url="https://ge.globo.com/futebol/flamengo",
            source="GloboEsporte",
            mentions_lineup=True,
        )
    ],
    raw_data={"lineup_source": "news_sites"},
)
_EMPTY_RESULT = SportsQueryResult(
    query="A vs B",
    provider="lineup_detector",
    success=False,
    error="not found",
)


def test_get_window_matches_inside():
    poller = APEXLineupPoller(_make_context([_match_dict("Flu", "Bot", 45)]), _make_telegram())
    assert len(poller._get_window_matches()) == 1


def test_get_window_matches_too_early():
    poller = APEXLineupPoller(_make_context([_match_dict("Flu", "Bot", 120)]), _make_telegram())
    assert poller._get_window_matches() == []


def test_get_window_matches_too_late():
    poller = APEXLineupPoller(_make_context([_match_dict("Flu", "Bot", 2)]), _make_telegram())
    assert poller._get_window_matches() == []


def test_get_window_matches_multiple():
    poller = APEXLineupPoller(
        _make_context(
            [
                _match_dict("A", "B", 60),
                _match_dict("C", "D", 30),
                _match_dict("E", "F", 100),
            ]
        ),
        _make_telegram(),
    )
    assert len(poller._get_window_matches()) == 2


@pytest.mark.asyncio
async def test_check_lineups_both_confirmed():
    from skills.webmcp.sports.lineup_detector import LineupDetector

    poller = APEXLineupPoller(_make_context([]), _make_telegram())
    with patch.object(
        LineupDetector,
        "detect_lineups",
        new_callable=AsyncMock,
        return_value=_RESULT_WITH_LINEUPS,
    ):
        status = await poller._check_lineups("Flamengo", "Palmeiras", "Brasileirão", 999)

    assert status["both_confirmed"] is True
    assert status["home_starters"] == ["Gerson", "Pedro"]
    assert status["source"] == "sofascore_api"


@pytest.mark.asyncio
async def test_check_lineups_news_only():
    from skills.webmcp.sports.lineup_detector import LineupDetector

    poller = APEXLineupPoller(_make_context([]), _make_telegram())
    with patch.object(
        LineupDetector,
        "detect_lineups",
        new_callable=AsyncMock,
        return_value=_NEWS_RESULT,
    ):
        status = await poller._check_lineups("Flamengo", "Palmeiras", "Brasileirão", 999)

    assert status["both_confirmed"] is False
    assert status["lineup_news"] == 1
    assert status["source"] == "news_sites"


@pytest.mark.asyncio
async def test_check_lineups_error_returns_safe_dict():
    from skills.webmcp.sports.lineup_detector import LineupDetector

    poller = APEXLineupPoller(_make_context([]), _make_telegram())
    with patch.object(
        LineupDetector,
        "detect_lineups",
        new_callable=AsyncMock,
        side_effect=Exception("timeout"),
    ):
        status = await poller._check_lineups("A", "B", "Liga", 1)

    assert status["both_confirmed"] is False
    assert status["source"] == "error"


@pytest.mark.asyncio
async def test_handle_status_sends_full_confirmation_and_persists():
    ctx = _make_context([])
    telegram = _make_telegram()
    poller = APEXLineupPoller(ctx, telegram)

    await poller._handle_status(
        1,
        "Flamengo",
        "Palmeiras",
        "Brasileirão",
        {
            "both_confirmed": True,
            "home_confirmed": True,
            "away_confirmed": True,
            "source": "sofascore_api",
            "lineup_news": 0,
            "home_starters": ["Gerson"],
            "away_starters": ["Weverton"],
            "home_formation": "4-3-3",
            "away_formation": "4-4-2",
        },
    )

    telegram.send.assert_called_once()
    assert 1 in poller._notified_full
    assert 1 in ctx._context["lineups_confirmed"]
    ctx._save.assert_called_once()


@pytest.mark.asyncio
async def test_handle_status_no_duplicate_full():
    ctx = _make_context([])
    telegram = _make_telegram()
    poller = APEXLineupPoller(ctx, telegram)
    poller._notified_full.add(1)

    await poller._handle_status(
        1,
        "Flamengo",
        "Palmeiras",
        "Brasileirão",
        {
            "both_confirmed": True,
            "home_confirmed": True,
            "away_confirmed": True,
            "source": "sofascore_api",
            "lineup_news": 0,
        },
    )

    telegram.send.assert_not_called()


@pytest.mark.asyncio
async def test_handle_status_partial_notification_with_team():
    telegram = _make_telegram()
    poller = APEXLineupPoller(_make_context([]), telegram)

    await poller._handle_status(
        2,
        "Flamengo",
        "Palmeiras",
        "Brasileirão",
        {
            "both_confirmed": False,
            "home_confirmed": True,
            "away_confirmed": False,
            "source": "sofascore_api",
            "lineup_news": 0,
        },
    )

    telegram.send.assert_called_once()
    assert 2 in poller._notified_partial


@pytest.mark.asyncio
async def test_handle_status_news_triggers_partial():
    telegram = _make_telegram()
    poller = APEXLineupPoller(_make_context([]), telegram)

    await poller._handle_status(
        3,
        "A",
        "B",
        "BR",
        {
            "both_confirmed": False,
            "home_confirmed": False,
            "away_confirmed": False,
            "source": "news_sites",
            "lineup_news": 2,
        },
    )

    telegram.send.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_webmcp_lineups_with_sofascore():
    from skills.webmcp.sports.lineup_detector import LineupDetector

    with patch.object(
        LineupDetector,
        "detect_lineups",
        new_callable=AsyncMock,
        return_value=_RESULT_WITH_LINEUPS,
    ):
        result = await _fetch_webmcp_lineups("Flamengo", "Palmeiras", "Brasileirão")

    assert result["home_lineup"] == ["Gerson", "Pedro"]
    assert result["away_lineup"] == ["Weverton"]
    assert result["source"] == "sofascore_api"


@pytest.mark.asyncio
async def test_fetch_webmcp_lineups_fallback_news():
    from skills.webmcp.sports.lineup_detector import LineupDetector

    with patch.object(
        LineupDetector,
        "detect_lineups",
        new_callable=AsyncMock,
        return_value=_NEWS_RESULT,
    ):
        result = await _fetch_webmcp_lineups("Flamengo", "Palmeiras", "Brasileirão")

    assert "news_articles" in result
    assert result["source"] == "news_sites"


@pytest.mark.asyncio
async def test_fetch_webmcp_lineups_empty_on_error():
    from skills.webmcp.sports.lineup_detector import LineupDetector

    with patch.object(
        LineupDetector,
        "detect_lineups",
        new_callable=AsyncMock,
        side_effect=Exception("network error"),
    ):
        result = await _fetch_webmcp_lineups("X", "Y", "Liga")

    assert result == {}


@pytest.mark.asyncio
async def test_fetch_webmcp_lineups_empty_result():
    from skills.webmcp.sports.lineup_detector import LineupDetector

    with patch.object(
        LineupDetector,
        "detect_lineups",
        new_callable=AsyncMock,
        return_value=_EMPTY_RESULT,
    ):
        result = await _fetch_webmcp_lineups("X", "Y", "Liga")

    assert result == {}


def test_format_full_confirmation_contains_teams():
    poller = APEXLineupPoller(_make_context([]), _make_telegram())
    msg = poller._format_full_confirmation(
        "Flamengo",
        "Palmeiras",
        "Brasileirão",
        {
            "home_starters": ["Gerson", "Pedro"],
            "away_starters": ["Weverton"],
            "home_formation": "4-3-3",
            "away_formation": "4-4-2",
        },
        "sofascore_api",
    )

    assert "Flamengo" in msg
    assert "Palmeiras" in msg
    assert "Brasileirão" in msg
    assert "sofascore_api" in msg


def test_format_partial_shows_confirmed_team():
    poller = APEXLineupPoller(_make_context([]), _make_telegram())
    msg = poller._format_partial_notification(
        "Flamengo",
        "Palmeiras",
        "Brasileirão",
        {"home_confirmed": True, "away_confirmed": False, "lineup_news": 0},
    )

    assert "Flamengo" in msg
    assert "confirmado" in msg.lower()
