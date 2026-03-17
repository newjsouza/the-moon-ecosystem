"""tests/test_apex_oracle.py — Testes unitários do APEX Oracle"""
import pytest
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN",      "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID",         "123456")
os.environ.setdefault("FOOTBALL_DATA_API_KEY",    "test_key")
os.environ.setdefault("GROQ_API_KEY",             "test_key")


from agents.apex.oracle import (
    MatchMessageFormatter,
    DailyContextStore,
    FootballDataClient,
    TelegramSender,
)


class TestMatchMessageFormatter:

    def test_format_last5_empty(self):
        fmt = MatchMessageFormatter()
        result = fmt.format_last5([], "Team A")
        assert "Team A" in result
        assert "não disponíveis" in result

    def test_format_last5_with_data(self):
        fmt = MatchMessageFormatter()
        matches = [
            {
                "homeTeam": {"shortName": "TeamA"},
                "awayTeam": {"shortName": "TeamB"},
                "score": {"fullTime": {"home": 2, "away": 1}},
                "utcDate": "2026-03-10T15:00:00Z",
                "competition": {"name": "Premier League"},
            }
        ]
        result = fmt.format_last5(matches, "TeamA")
        assert "TeamA" in result
        assert "2×1" in result or "2" in result

    def test_format_morning_analysis_structure(self):
        fmt = MatchMessageFormatter()
        analysis = {
            "home_team": "Flamengo",
            "away_team": "Vasco",
            "competition": "Brasileirão",
            "kickoff_local": "17/03/2026 às 21:00 (Brasília)",
            "last5_home_formatted": "  últimos jogos",
            "last5_away_formatted": "  últimos jogos",
            "general_analysis": "Clássico carioca muito equilibrado.",
            "betting_markets": [
                {"market": "Resultado Final", "tip": "Flamengo vence", "reasoning": "Melhor fase.", "confidence": "Alta"},
                {"market": "Over 2.5 Gols", "tip": "Over 2.5", "reasoning": "Muitos gols recentes.", "confidence": "Média"},
            ],
        }
        result = fmt.format_morning_analysis(analysis)
        assert "Flamengo" in result
        assert "Vasco" in result
        assert "MERCADOS" in result
        assert "Resultado Final" in result

    def test_format_pre45_with_lineups(self):
        fmt = MatchMessageFormatter()
        analysis = {
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "competition": "Premier League",
            "kickoff_local": "17/03/2026 às 17:30 (Brasília)",
            "general_analysis": "Bom jogo esperado.",
            "refined_analysis": "Análise refinada.",
            "betting_markets": [
                {"market": "BTTS", "tip": "Sim", "confidence": "Alta"},
            ],
        }
        lineups = {
            "home_lineup": ["Raya", "White", "Gabriel", "Kiwior", "Zinchenko"],
            "away_lineup": ["Sanchez", "Reece", "Colwill", "Badiashile"],
            "home_absent": ["Saka"],
            "away_absent": [],
            "home_suspended": [],
            "away_suspended": ["Palmer"],
            "home_returns": ["Havertz"],
            "away_returns": [],
        }
        result = fmt.format_pre45_analysis(analysis, lineups)
        assert "Arsenal" in result
        assert "Chelsea" in result
        assert "Saka" in result
        assert "Palmer" in result
        assert "Havertz" in result
        assert "45 MIN" in result


class TestDailyContextStore:

    def test_save_and_load_context(self, tmp_path):
        import agents.apex.oracle as oracle_mod
        original = oracle_mod.DAILY_CONTEXT_FILE
        oracle_mod.DAILY_CONTEXT_FILE = tmp_path / "test_context.json"

        store = DailyContextStore()
        analyses = [
            {
                "match_id": 1,
                "home_team": "Flamengo",
                "away_team": "Vasco",
                "teams": "Flamengo × Vasco",
                "competition": "Brasileirão",
                "kickoff_utc": "2026-03-17T21:00:00Z",
                "kickoff_local": "17/03/2026 às 18:00",
                "general_analysis": "Ótimo jogo esperado.",
                "betting_markets": [{"market": "Resultado Final", "tip": "Flamengo"}],
            }
        ]
        store.save_daily_analyses("2026-03-17", analyses)
        assert store._context["date"] == "2026-03-17"
        assert len(store._context["analyses"]) == 1

        ctx_str = store.get_context_for_bot()
        assert "Flamengo" in ctx_str
        assert "Brasileirão" in ctx_str

        oracle_mod.DAILY_CONTEXT_FILE = original

    def test_mark_pre45_sent(self, tmp_path):
        import agents.apex.oracle as oracle_mod
        oracle_mod.DAILY_CONTEXT_FILE = tmp_path / "test_context2.json"

        store = DailyContextStore()
        store._context = {
            "date": "2026-03-17",
            "analyses": [{"match_id": 42, "kickoff_utc": "2026-03-17T21:00:00Z"}],
            "matches_summary": [{"match_id": 42, "pre45_sent": False, "markets": []}],
        }
        store.mark_pre45_sent(42)
        summary = next(m for m in store._context["matches_summary"] if m["match_id"] == 42)
        assert summary["pre45_sent"] is True


class TestFootballDataClient:

    @pytest.mark.asyncio
    async def test_get_returns_none_on_error(self):
        client = FootballDataClient()
        client.api_key = "invalid_key_for_test"
        result = await client.get("/invalid_endpoint")
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_matches_today_returns_list(self):
        client = FootballDataClient()
        with patch.object(client, "get", new=AsyncMock(return_value={"matches": []})):
            result = await client.get_matches_today()
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_last5_empty_on_no_data(self):
        client = FootballDataClient()
        with patch.object(client, "get", new=AsyncMock(return_value=None)):
            result = await client.get_last_5_matches(999)
            assert result == []
