"""
core/kelly.py — Kelly Criterion engine for The Moon Hedge system.

Implements:
  - Full Kelly (theoretical maximum)
  - Fractional Kelly (recommended: 0.25x for safety)
  - Kelly with edge threshold (minimum EV to bet)
  - Monte Carlo simulation (N paths, configurable)
  - Drawdown protection (stop betting when DD > limit)
  - Value Bet detection (implied probability vs estimated)

Mathematical foundation:
  Kelly fraction f* = (bp - q) / b
    b = decimal_odd - 1 (net return)
    p = estimated win probability
    q = 1 - p (loss probability)
    EV = b * p - q (expected value per unit)

Reference: J.L. Kelly Jr., "A New Interpretation of Information Rate", 1956.
"""
import math
import random
import logging
from dataclasses import dataclass, field
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class BetRecommendation:
    """
    Complete bet recommendation output from Kelly engine.
    All amounts in units (% of bankroll).
    """
    match_id: str
    home_team: str
    away_team: str
    market: str                         # "home_win", "draw", "away_win", "over_2.5"
    decimal_odd: float
    estimated_probability: float        # our model probability
    implied_probability: float          # market implied = 1 / odd
    edge: float                         # our_prob - implied_prob
    expected_value: float               # EV per unit staked
    kelly_full: float                   # full Kelly fraction
    kelly_fraction: float               # fractional Kelly (recommended)
    stake_units: float                  # final stake as % of bankroll
    stake_amount: float                 # stake in currency (bankroll * stake_units)
    confidence: str                     # "high" | "medium" | "low"
    apex_approved: bool                 # passes all APEX rules
    apex_warnings: list = field(default_factory=list)
    reasoning: str = ""


@dataclass
class BacktestResult:
    """Results from a historical backtesting run."""
    total_bets: int
    wins: int
    losses: int
    win_rate: float
    roi: float                          # Return on Investment %
    total_profit_units: float
    max_drawdown: float                 # worst peak-to-trough %
    avg_stake_units: float
    avg_edge: float
    sharpe_ratio: float
    kelly_calibration: float            # avg(kelly_used / kelly_optimal)
    simulation_paths: list = field(default_factory=list)
    period_start: str = ""
    period_end: str = ""


class KellyEngine:
    """
    Scientific bet sizing engine.
    Use fractional Kelly (0.25x) to reduce variance while preserving edge.
    """

    # ── APEX v2 Hard Limits ────────────────────────────────────
    APEX_MAX_STAKE_PCT = 0.05           # 5% max per bet
    APEX_MIN_PROBABILITY = 0.40        # 40% min estimated prob
    APEX_MIN_EDGE = 0.03               # 3% minimum edge to bet
    APEX_MIN_EV = 0.02                 # 2% minimum EV
    APEX_STOP_LOSS_PCT = 0.12          # stop betting at 12% bankroll loss
    APEX_MAX_DRAWDOWN_PCT = 0.20       # emergency stop at 20% drawdown
    APEX_MAX_CONCURRENT = 3            # max simultaneous open bets
    KELLY_FRACTION = 0.25              # 25% of full Kelly

    def __init__(self, bankroll: float = 1000.0):
        """
        Args:
            bankroll: current bankroll in any currency unit.
                      Default 1000 = percentage-based (1 unit = 0.1%).
        """
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        self._current_drawdown = 0.0
        self._open_bets = 0
        self._session_loss = 0.0

    def calculate(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        market: str,
        decimal_odd: float,
        estimated_probability: float,
        reasoning: str = "",
    ) -> BetRecommendation:
        """
        Calculate full BetRecommendation with Kelly sizing and APEX validation.

        Args:
            match_id: unique match identifier
            home_team, away_team: team names
            market: bet market (home_win, draw, away_win, over_2.5, btts)
            decimal_odd: bookmaker decimal odd (e.g. 2.10)
            estimated_probability: our model probability (0.0 to 1.0)
            reasoning: explanation of probability estimation
        """
        if decimal_odd <= 1.0:
            raise ValueError(f"decimal_odd must be > 1.0, got {decimal_odd}")
        if not 0.0 < estimated_probability < 1.0:
            raise ValueError(
                f"estimated_probability must be 0 < p < 1, got {estimated_probability}"
            )

        b = decimal_odd - 1.0                       # net odd
        p = estimated_probability
        q = 1.0 - p                                 # loss probability
        implied_prob = 1.0 / decimal_odd
        edge = p - implied_prob
        ev = b * p - q                              # expected value

        # Full Kelly
        if b > 0:
            kelly_full = max(0.0, (b * p - q) / b)
        else:
            kelly_full = 0.0

        # Fractional Kelly
        kelly_frac = kelly_full * self.KELLY_FRACTION

        # APEX validation
        approved, warnings = self._apex_check(
            p, edge, ev, kelly_frac, decimal_odd
        )

        # Final stake (APEX-capped)
        stake_units = min(kelly_frac, self.APEX_MAX_STAKE_PCT) if approved else 0.0
        stake_amount = self.bankroll * stake_units

        # Confidence tier
        if edge >= 0.10 and p >= 0.55:
            confidence = "high"
        elif edge >= 0.05 and p >= 0.45:
            confidence = "medium"
        else:
            confidence = "low"

        return BetRecommendation(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            market=market,
            decimal_odd=decimal_odd,
            estimated_probability=p,
            implied_probability=implied_prob,
            edge=round(edge, 4),
            expected_value=round(ev, 4),
            kelly_full=round(kelly_full, 4),
            kelly_fraction=round(kelly_frac, 4),
            stake_units=round(stake_units, 4),
            stake_amount=round(stake_amount, 2),
            confidence=confidence,
            apex_approved=approved,
            apex_warnings=warnings,
            reasoning=reasoning,
        )

    def monte_carlo(
        self,
        win_probability: float,
        stake_fraction: float,
        n_bets: int = 100,
        n_paths: int = 1000,
        decimal_odd: float = 2.0,
        seed: Optional[int] = None,
    ) -> dict:
        """
        Monte Carlo simulation of bet sequence.
        Returns distribution of outcomes across N paths.

        Args:
            win_probability: estimated win probability per bet
            stake_fraction: fraction of bankroll per bet (e.g. 0.025)
            n_bets: number of bets per simulation path
            n_paths: number of simulation paths
            decimal_odd: decimal odd for wins
            seed: random seed for reproducibility
        """
        if seed is not None:
            random.seed(seed)

        rng = random.Random(seed)
        final_bankrolls = []
        max_drawdowns = []

        for _ in range(n_paths):
            bankroll = 1.0          # normalized to 1.0
            peak = 1.0
            max_dd = 0.0

            for _ in range(n_bets):
                stake = bankroll * stake_fraction
                if rng.random() < win_probability:
                    bankroll += stake * (decimal_odd - 1.0)
                else:
                    bankroll -= stake

                bankroll = max(0.001, bankroll)  # prevent zero
                peak = max(peak, bankroll)
                drawdown = (peak - bankroll) / peak
                max_dd = max(max_dd, drawdown)

                # APEX emergency stop
                if drawdown > self.APEX_MAX_DRAWDOWN_PCT:
                    break

            final_bankrolls.append(round(bankroll, 4))
            max_drawdowns.append(round(max_dd, 4))

        sorted_brs = sorted(final_bankrolls)
        n = len(sorted_brs)

        return {
            "n_paths": n_paths,
            "n_bets": n_bets,
            "win_probability": win_probability,
            "stake_fraction": stake_fraction,
            "median_final": sorted_brs[n // 2],
            "p10_final": sorted_brs[int(n * 0.10)],    # 10th percentile
            "p90_final": sorted_brs[int(n * 0.90)],    # 90th percentile
            "ruin_probability": sum(1 for b in final_bankrolls if b < 0.1) / n,
            "profit_probability": sum(1 for b in final_bankrolls if b > 1.0) / n,
            "avg_max_drawdown": round(sum(max_drawdowns) / len(max_drawdowns), 4),
            "paths_sample": final_bankrolls[:10],       # sample for charts
        }

    def backtest(self, bet_history: list) -> BacktestResult:
        """
        Backtest Kelly performance on historical bet data.

        Args:
            bet_history: list of dicts with keys:
                match_id, decimal_odd, estimated_probability,
                stake_fraction (used), outcome (True=win, False=loss),
                date (str)
        """
        if not bet_history:
            return BacktestResult(
                total_bets=0, wins=0, losses=0, win_rate=0.0,
                roi=0.0, total_profit_units=0.0, max_drawdown=0.0,
                avg_stake_units=0.0, avg_edge=0.0, sharpe_ratio=0.0,
                kelly_calibration=0.0,
            )

        bankroll = 1.0
        peak = 1.0
        max_dd = 0.0
        profits = []
        edges = []
        kelly_ratios = []
        wins = 0

        for bet in bet_history:
            decimal_odd = bet.get("decimal_odd", 2.0)
            p = bet.get("estimated_probability", 0.5)
            stake_frac = bet.get("stake_fraction", 0.02)
            outcome = bet.get("outcome", False)

            # Compute optimal Kelly for this bet
            b = decimal_odd - 1.0
            kelly_opt = max(0.0, (b * p - (1 - p)) / b) if b > 0 else 0.0
            kelly_opt_frac = kelly_opt * self.KELLY_FRACTION
            if kelly_opt_frac > 0:
                kelly_ratios.append(stake_frac / kelly_opt_frac)

            stake = bankroll * stake_frac
            if outcome:
                profit = stake * b
                wins += 1
            else:
                profit = -stake

            bankroll += profit
            bankroll = max(0.001, bankroll)
            profits.append(profit)

            peak = max(peak, bankroll)
            dd = (peak - bankroll) / peak
            max_dd = max(max_dd, dd)

            implied = 1.0 / decimal_odd
            edges.append(p - implied)

        n = len(bet_history)
        total_profit = bankroll - 1.0
        roi = total_profit / 1.0 * 100

        # Sharpe ratio (annualized, assuming 1 bet/week → 52 bets/year)
        if len(profits) > 1:
            mean_p = sum(profits) / len(profits)
            variance = sum((x - mean_p) ** 2 for x in profits) / len(profits)
            std_p = math.sqrt(variance) if variance > 0 else 0.001
            sharpe = (mean_p / std_p) * math.sqrt(52)
        else:
            sharpe = 0.0

        return BacktestResult(
            total_bets=n,
            wins=wins,
            losses=n - wins,
            win_rate=round(wins / n * 100, 1),
            roi=round(roi, 2),
            total_profit_units=round(total_profit, 4),
            max_drawdown=round(max_dd * 100, 2),
            avg_stake_units=round(
                sum(b.get("stake_fraction", 0) for b in bet_history) / n, 4
            ),
            avg_edge=round(sum(edges) / len(edges), 4) if edges else 0.0,
            sharpe_ratio=round(sharpe, 3),
            kelly_calibration=round(
                sum(kelly_ratios) / len(kelly_ratios), 3
            ) if kelly_ratios else 1.0,
            period_start=bet_history[0].get("date", ""),
            period_end=bet_history[-1].get("date", ""),
        )

    def update_bankroll(self, amount: float) -> None:
        """Update bankroll after bet resolution."""
        self.bankroll += amount
        self.bankroll = max(0.0, self.bankroll)
        peak = self.initial_bankroll
        self._current_drawdown = max(
            0.0, (peak - self.bankroll) / peak
        ) if peak > 0 else 0.0

    def _apex_check(
        self,
        p: float,
        edge: float,
        ev: float,
        kelly_frac: float,
        decimal_odd: float,
    ) -> tuple:
        """Apply APEX v2 rules. Returns (approved, warnings)."""
        warnings = []

        if p < self.APEX_MIN_PROBABILITY:
            warnings.append(
                f"APEX: prob {p:.1%} < min {self.APEX_MIN_PROBABILITY:.1%}"
            )
        if edge < self.APEX_MIN_EDGE:
            warnings.append(
                f"APEX: edge {edge:.1%} < min {self.APEX_MIN_EDGE:.1%}"
            )
        if ev < self.APEX_MIN_EV:
            warnings.append(
                f"APEX: EV {ev:.1%} < min {self.APEX_MIN_EV:.1%}"
            )
        if kelly_frac <= 0:
            warnings.append("APEX: Kelly fraction ≤ 0 — negative edge")
        if self._current_drawdown >= self.APEX_STOP_LOSS_PCT:
            warnings.append(
                f"APEX: drawdown {self._current_drawdown:.1%} ≥ "
                f"stop-loss {self.APEX_STOP_LOSS_PCT:.1%}"
            )
        if self._open_bets >= self.APEX_MAX_CONCURRENT:
            warnings.append(
                f"APEX: {self._open_bets} open bets ≥ max {self.APEX_MAX_CONCURRENT}"
            )

        approved = len(warnings) == 0
        return approved, warnings
