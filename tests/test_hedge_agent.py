"""
Tests for HedgeAgent v2, KellyEngine and BetRecommendation.
Zero network calls. Zero API keys required.
"""
import pytest
import math
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestKellyEngine:

    def setup_method(self):
        from core.kelly import KellyEngine
        self.engine = KellyEngine(bankroll=1000.0)

    def test_import(self):
        from core.kelly import KellyEngine, BetRecommendation, BacktestResult
        assert KellyEngine is not None

    def test_calculate_positive_edge(self):
        rec = self.engine.calculate(
            "m001", "Flamengo", "Palmeiras",
            "home_win", 2.10, 0.55
        )
        assert rec.edge > 0
        assert rec.expected_value > 0
        assert rec.kelly_full > 0
        assert rec.kelly_fraction > 0
        assert rec.stake_units <= self.engine.APEX_MAX_STAKE_PCT

    def test_calculate_negative_edge_rejected(self):
        rec = self.engine.calculate(
            "m002", "Team A", "Team B",
            "away_win", 1.80, 0.40
        )
        # edge = 0.40 - 1/1.80 = 0.40 - 0.556 = -0.156 (negative)
        assert rec.edge < 0
        assert not rec.apex_approved
        assert len(rec.apex_warnings) > 0

    def test_kelly_fraction_is_25pct_of_full(self):
        rec = self.engine.calculate(
            "m003", "A", "B", "home_win", 2.50, 0.55
        )
        assert abs(rec.kelly_fraction - rec.kelly_full * 0.25) < 1e-6

    def test_stake_capped_at_apex_max(self):
        # Very high edge should still be capped at 5%
        rec = self.engine.calculate(
            "m004", "A", "B", "home_win", 5.0, 0.90
        )
        assert rec.stake_units <= self.engine.APEX_MAX_STAKE_PCT

    def test_apex_rejects_low_probability(self):
        rec = self.engine.calculate(
            "m005", "A", "B", "draw", 4.0, 0.35
        )
        assert not rec.apex_approved
        assert any("prob" in w for w in rec.apex_warnings)

    def test_apex_rejects_zero_edge(self):
        # Exact fair odds: p = 1/odd
        odd = 2.0
        p = 1.0 / odd  # 0.50 — zero edge
        rec = self.engine.calculate("m006", "A", "B", "home_win", odd, p)
        assert not rec.apex_approved

    def test_confidence_high(self):
        rec = self.engine.calculate(
            "m007", "A", "B", "home_win", 2.50, 0.65
        )
        assert rec.confidence in ("high", "medium", "low")

    def test_decimal_odd_below_one_raises(self):
        with pytest.raises(ValueError):
            self.engine.calculate("m008", "A", "B", "home_win", 0.80, 0.60)

    def test_probability_out_of_bounds_raises(self):
        with pytest.raises(ValueError):
            self.engine.calculate("m009", "A", "B", "home_win", 2.0, 1.10)

    def test_implied_probability_calculation(self):
        odd = 2.50
        rec = self.engine.calculate("m010", "A", "B", "home_win", odd, 0.55)
        assert abs(rec.implied_probability - 1.0 / odd) < 1e-6

    def test_update_bankroll(self):
        self.engine.update_bankroll(100.0)
        assert self.engine.bankroll == 1100.0
        self.engine.update_bankroll(-200.0)
        assert self.engine.bankroll == 900.0

    def test_backtest_empty(self):
        result = self.engine.backtest([])
        assert result.total_bets == 0
        assert result.roi == 0.0

    def test_backtest_all_wins(self):
        history = [
            {"decimal_odd": 2.0, "estimated_probability": 0.60,
             "stake_fraction": 0.02, "outcome": True, "date": "2026-01-01"}
            for _ in range(20)
        ]
        result = self.engine.backtest(history)
        assert result.wins == 20
        assert result.losses == 0
        assert result.win_rate == 100.0
        assert result.roi > 0

    def test_backtest_all_losses(self):
        history = [
            {"decimal_odd": 2.0, "estimated_probability": 0.60,
             "stake_fraction": 0.02, "outcome": False, "date": "2026-01-01"}
            for _ in range(20)
        ]
        result = self.engine.backtest(history)
        assert result.wins == 0
        assert result.losses == 20
        assert result.roi < 0

    def test_backtest_result_fields(self):
        history = [
            {"decimal_odd": 2.10, "estimated_probability": 0.55,
             "stake_fraction": 0.025, "outcome": i % 2 == 0, "date": "2026-01-01"}
            for i in range(10)
        ]
        result = self.engine.backtest(history)
        assert result.total_bets == 10
        assert result.win_rate == 50.0
        assert result.max_drawdown >= 0.0
        assert result.sharpe_ratio is not None

    def test_monte_carlo_structure(self):
        result = self.engine.monte_carlo(
            win_probability=0.55,
            stake_fraction=0.025,
            n_bets=50,
            n_paths=100,
            decimal_odd=2.10,
            seed=42,
        )
        assert "median_final" in result
        assert "ruin_probability" in result
        assert "profit_probability" in result
        assert 0.0 <= result["ruin_probability"] <= 1.0

    def test_monte_carlo_positive_edge_profit(self):
        result = self.engine.monte_carlo(
            win_probability=0.60,
            stake_fraction=0.02,
            n_bets=100,
            n_paths=500,
            decimal_odd=2.20,
            seed=123,
        )
        assert result["profit_probability"] > 0.5

    def test_monte_carlo_negative_edge_ruin(self):
        result = self.engine.monte_carlo(
            win_probability=0.35,
            stake_fraction=0.05,
            n_bets=100,
            n_paths=500,
            decimal_odd=2.0,
            seed=99,
        )
        assert result["profit_probability"] < 0.5


class TestHedgeAgent:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        Path_mkdir_patcher = patch("pathlib.Path.mkdir")
        self._p = Path_mkdir_patcher.start()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        self._p.stop()

    def test_import(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)
        assert agent.AGENT_ID == "hedge"

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)
        result = await agent._execute("invalid")
        assert result.success is False
        assert "Unknown command" in result.error

    @pytest.mark.asyncio
    async def test_bankroll_status(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)
        result = await agent._execute("bankroll")
        assert result.success is True
        assert "current_bankroll" in result.data
        assert "pnl" in result.data

    @pytest.mark.asyncio
    async def test_simulate_command(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)
        result = await agent._execute(
            "simulate",
            win_probability=0.55,
            stake_fraction=0.025,
            n_paths=100,
            n_bets=50,
            decimal_odd=2.10,
            seed=42,
        )
        assert result.success is True
        assert "median_final" in result.data
        assert "ruin_probability" in result.data

    @pytest.mark.asyncio
    async def test_analyze_no_matches(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)
        with patch.object(agent, "_fetch_upcoming_matches",
                          new_callable=AsyncMock,
                          return_value=[]):
            result = await agent._execute("analyze", competition="BSA")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_analyze_with_mock_matches(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)

        mock_matches = [
            {
                "id": "001",
                "homeTeam": {"name": "Flamengo"},
                "awayTeam": {"name": "Palmeiras"},
                "competition": {"name": "Brasileirão"},
                "utcDate": "2026-03-22T20:00:00Z",
            }
        ]

        mock_llm_response = (
            '{"home_win_probability": 0.55,'
            '"draw_probability": 0.25,'
            '"away_win_probability": 0.20,'
            '"recommended_market": "home_win",'
            '"recommended_odd": 2.10,'
            '"reasoning": "Flamengo forte em casa"}'
        )

        with patch.object(agent, "_fetch_upcoming_matches",
                          new_callable=AsyncMock,
                          return_value=mock_matches), \
             patch.object(agent.llm, "complete",
                          new_callable=AsyncMock,
                          return_value=mock_llm_response), \
             patch.object(agent, "_get_rag_context",
                          new_callable=AsyncMock,
                          return_value=""):
            result = await agent._execute("analyze", competition="BSA")

        assert result.success is True
        assert result.data["matches_analyzed"] >= 1

    @pytest.mark.asyncio
    async def test_pipeline_dry_run_no_matches(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)
        with patch.object(agent, "_fetch_upcoming_matches",
                          new_callable=AsyncMock,
                          return_value=[]):
            result = await agent._execute(
                "pipeline", competition="BSA", dry_run=True
            )
        assert result.success is False
        assert "No upcoming matches" in result.error

    @pytest.mark.asyncio
    async def test_backtest_insufficient_history(self):
        from agents.hedge_agent import HedgeAgent
        agent = HedgeAgent(bankroll=1000.0)
        with patch("core.rag.RAGEngine") as mock_rag_cls:
            mock_rag = mock_rag_cls.return_value
            mock_rag.search = AsyncMock(return_value=[])
            result = await agent._execute("backtest")
        assert result.success is True
        assert "history_count" in result.data
