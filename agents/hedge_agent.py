"""
HedgeAgent v2 — Scientific sports betting automation.

Architecture:
  KellyEngine (core/kelly.py) — mathematical core
  SportsAnalyticsAgent — match data + predictions
  RAGEngine — historical context + anti-repetition
  LLMRouter — narrative probability estimation

Commands:
  'analyze'    → analyze matches + generate recommendations
  'backtest'   → run backtest on RAG historical data
  'simulate'   → Monte Carlo simulation for given parameters
  'report'     → generate Telegram report (recommendations + stats)
  'bankroll'   → show current bankroll status + open bets
  'pipeline'   → full auto: fetch matches → analyze → report
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from core.agent_base import AgentBase, TaskResult
from core.observability.decorators import observe_agent
from agents.llm import LLMRouter
from core.kelly import KellyEngine, BetRecommendation
from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


@observe_agent
class HedgeAgent(AgentBase):
    """
    HedgeAgent v2 — Kelly + APEX v2 + Monte Carlo + Backtesting.
    Zero cost: football-data.org free tier + Groq.
    """

    AGENT_ID = "hedge"

    # Default competitions to analyze
    DEFAULT_COMPETITIONS = [
        "BSA",   # Brasileirão Série A
        "PL",    # Premier League
        "CL",    # Champions League
    ]

    # Bankroll persistence path
    BANKROLL_PATH = Path("data/hedge/bankroll.json")

    def __init__(self, bankroll: float = 1000.0):
        super().__init__()
        self.llm = LLMRouter()
        self._sports_cb = CircuitBreaker(
            "sports_api_hedge",
            CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=120.0,
                timeout=15.0,
            )
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        self.kelly = self._load_or_create_engine(bankroll)
        Path("data/hedge").mkdir(parents=True, exist_ok=True)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute HedgeAgent command.
        kwargs:
            competition (str): competition code (BSA, PL, CL...)
            competitions (list): multiple competitions
            bankroll (float): override current bankroll
            dry_run (bool): skip Telegram notification
            n_paths (int): Monte Carlo paths (default 1000)
            n_bets (int): Monte Carlo bets per path (default 100)
        """
        start = asyncio.get_event_loop().time()
        cmd = task.lower().strip()

        try:
            if cmd == "pipeline":
                return await self._run_pipeline(kwargs, start)
            elif cmd == "analyze":
                return await self._analyze_matches(kwargs, start)
            elif cmd == "backtest":
                return await self._run_backtest(kwargs, start)
            elif cmd == "simulate":
                return await self._run_simulation(kwargs, start)
            elif cmd == "report":
                return await self._generate_report(kwargs, start)
            elif cmd == "bankroll":
                return await self._bankroll_status(start)
            else:
                return TaskResult(
                    success=False,
                    error=(
                        f"Unknown command: '{cmd}'. "
                        "Valid: pipeline, analyze, backtest, simulate, "
                        "report, bankroll"
                    )
                )
        except Exception as e:
            self.logger.error(f"HedgeAgent error: {e}", exc_info=True)
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _run_pipeline(self, kwargs: dict, start: float) -> TaskResult:
        """Full pipeline: fetch → analyze → simulate → report."""
        competitions = kwargs.get(
            "competitions", kwargs.get(
                "competition", self.DEFAULT_COMPETITIONS[:1]
            )
        )
        if isinstance(competitions, str):
            competitions = [competitions]

        pipeline_data = {
            "competitions": competitions,
            "steps": [],
            "recommendations": [],
            "timestamp": datetime.now().isoformat(),
        }

        # Step 1: Fetch upcoming matches
        all_matches = []
        for comp in competitions:
            matches = await self._fetch_upcoming_matches(comp)
            all_matches.extend(matches)

        if not all_matches:
            return TaskResult(
                success=False,
                error="No upcoming matches found for given competitions"
            )
        pipeline_data["matches_found"] = len(all_matches)
        pipeline_data["steps"].append("fetch")

        # Step 2: Analyze + generate recommendations
        recs = await self._analyze_all_matches(all_matches)
        approved = [r for r in recs if r.apex_approved]
        pipeline_data["recommendations"] = [
            self._rec_to_dict(r) for r in approved
        ]
        pipeline_data["total_analyzed"] = len(recs)
        pipeline_data["apex_approved"] = len(approved)
        pipeline_data["steps"].append("analyze")

        # Step 3: Monte Carlo for top recommendation
        if approved:
            top = approved[0]
            sim = self.kelly.monte_carlo(
                win_probability=top.estimated_probability,
                stake_fraction=top.stake_units,
                n_bets=50,
                n_paths=kwargs.get("n_paths", 500),
                decimal_odd=top.decimal_odd,
                seed=42,
            )
            pipeline_data["simulation"] = sim
            pipeline_data["steps"].append("simulate")

        # Step 4: RAG index
        await self._index_recommendations_to_rag(pipeline_data)
        pipeline_data["steps"].append("rag_indexed")

        # Step 5: Telegram report
        if not kwargs.get("dry_run", False) and approved:
            await self._send_telegram_report(approved, pipeline_data)
            pipeline_data["steps"].append("telegram_notified")

        # Step 6: Persist bankroll state
        self._save_bankroll()

        return TaskResult(
            success=True,
            data=pipeline_data,
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _analyze_matches(self, kwargs: dict, start: float) -> TaskResult:
        """Analyze specific competition matches."""
        competition = kwargs.get("competition", self.DEFAULT_COMPETITIONS[0])
        matches = await self._fetch_upcoming_matches(competition)

        if not matches:
            return TaskResult(
                success=False,
                error=f"No matches found for {competition}"
            )

        recs = await self._analyze_all_matches(matches)
        return TaskResult(
            success=True,
            data={
                "competition": competition,
                "matches_analyzed": len(recs),
                "apex_approved": sum(1 for r in recs if r.apex_approved),
                "recommendations": [self._rec_to_dict(r) for r in recs],
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _run_backtest(self, kwargs: dict, start: float) -> TaskResult:
        """Backtest using RAG historical data."""
        try:
            from core.rag import RAGEngine
            rag = RAGEngine()
            history_results = await rag.search(
                query="bet recommendation outcome result",
                collection="hedge_history",
                top_k=100,
                threshold=0.3,
            )

            bet_history = []
            for item in history_results:
                meta = item.get("metadata", {})
                if "decimal_odd" in meta and "outcome" in meta:
                    bet_history.append(meta)

            if len(bet_history) < 5:
                return TaskResult(
                    success=True,
                    data={
                        "message": (
                            f"Only {len(bet_history)} historical bets in RAG "
                            f"(minimum 5 needed). Keep betting to build history!"
                        ),
                        "history_count": len(bet_history),
                    },
                    execution_time=asyncio.get_event_loop().time() - start
                )

            result = self.kelly.backtest(bet_history)
            return TaskResult(
                success=True,
                data={
                    "backtest": asdict(result),
                    "bets_analyzed": len(bet_history),
                },
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _run_simulation(self, kwargs: dict, start: float) -> TaskResult:
        """Monte Carlo simulation with custom parameters."""
        p = kwargs.get("win_probability", 0.50)
        stake = kwargs.get("stake_fraction", self.kelly.APEX_MAX_STAKE_PCT / 2)
        n_paths = kwargs.get("n_paths", 1000)
        n_bets = kwargs.get("n_bets", 100)
        odd = kwargs.get("decimal_odd", 2.0)

        result = self.kelly.monte_carlo(
            win_probability=p,
            stake_fraction=stake,
            n_bets=n_bets,
            n_paths=n_paths,
            decimal_odd=odd,
            seed=kwargs.get("seed"),
        )
        return TaskResult(
            success=True,
            data=result,
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _generate_report(self, kwargs: dict, start: float) -> TaskResult:
        """Generate report from cached recommendations."""
        competition = kwargs.get("competition", self.DEFAULT_COMPETITIONS[0])
        result = await self._analyze_matches(kwargs, start)
        if result.success and not kwargs.get("dry_run", False):
            recs = [r for r in self._dicts_to_recs(
                result.data.get("recommendations", [])
            ) if r.apex_approved]
            if recs:
                await self._send_telegram_report(recs, result.data)
        return result

    async def _bankroll_status(self, start: float) -> TaskResult:
        """Return current bankroll status."""
        state = self._load_bankroll_state()
        return TaskResult(
            success=True,
            data={
                "current_bankroll": self.kelly.bankroll,
                "initial_bankroll": self.kelly.initial_bankroll,
                "pnl": self.kelly.bankroll - self.kelly.initial_bankroll,
                "pnl_pct": round(
                    (self.kelly.bankroll / self.kelly.initial_bankroll - 1) * 100, 2
                ),
                "current_drawdown_pct": round(
                    self.kelly._current_drawdown * 100, 2
                ),
                "open_bets": self.kelly._open_bets,
                "apex_stop_loss_triggered": (
                    self.kelly._current_drawdown >= self.kelly.APEX_STOP_LOSS_PCT
                ),
                "history": state.get("history", [])[-10:],
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _fetch_upcoming_matches(self, competition: str) -> list:
        """Fetch upcoming matches from football-data.org via circuit breaker."""
        try:
            from skills.sports.api_client import FootballDataClient
            client = FootballDataClient()

            matches_raw = await self._sports_cb.call(
                asyncio.to_thread,
                client.get_matches,
                competition,
            )
            return matches_raw if isinstance(matches_raw, list) else []
        except Exception as e:
            self.logger.warning(f"Fetch matches failed for {competition}: {e}")
            return []

    async def _analyze_all_matches(self, matches: list) -> list:
        """Generate BetRecommendation for each match."""
        recommendations = []
        for match in matches[:10]:  # cap at 10 to save LLM quota
            try:
                rec = await self._analyze_single_match(match)
                if rec:
                    recommendations.append(rec)
            except Exception as e:
                self.logger.warning(f"Match analysis failed: {e}")
        return recommendations

    async def _analyze_single_match(self, match: dict) -> BetRecommendation | None:
        """Estimate probability and calculate Kelly for a single match."""
        home = match.get("homeTeam", {})
        away = match.get("awayTeam", {})
        home_name = home.get("name", home.get("shortName", "Home"))
        away_name = away.get("name", away.get("shortName", "Away"))
        match_id = str(match.get("id", "unknown"))

        # Get RAG context for these teams
        rag_context = await self._get_rag_context(home_name, away_name)

        # LLM probability estimation
        prompt = f"""You are a sports betting analyst.
Analyze this match and estimate win probabilities:

Match: {home_name} vs {away_name}
Competition: {match.get('competition', {}).get('name', 'Unknown')}
Date: {match.get('utcDate', 'TBD')}
Historical context: {rag_context[:400] if rag_context else 'No data available'}

Respond in JSON only:
{{
  "home_win_probability": 0.XX,
  "draw_probability": 0.XX,
  "away_win_probability": 0.XX,
  "recommended_market": "home_win" | "draw" | "away_win",
  "recommended_odd": 1.XX,
  "reasoning": "brief 1-sentence rationale"
}}

Rules: probabilities must sum to 1.0. Respond ONLY with valid JSON:"""

        try:
            response = await self.llm.complete(prompt, task_type="fast", actor="hedge_agent")
            start = response.find("{")
            end = response.rfind("}") + 1
            if start < 0 or end <= start:
                return None

            data = json.loads(response[start:end])
            market = data.get("recommended_market", "home_win")
            p_map = {
                "home_win": data.get("home_win_probability", 0.33),
                "draw": data.get("draw_probability", 0.33),
                "away_win": data.get("away_win_probability", 0.33),
            }
            estimated_p = p_map.get(market, 0.33)
            odd = float(data.get("recommended_odd", 2.0))
            odd = max(1.01, odd)

            return self.kelly.calculate(
                match_id=match_id,
                home_team=home_name,
                away_team=away_name,
                market=market,
                decimal_odd=odd,
                estimated_probability=estimated_p,
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            self.logger.warning(f"LLM analysis failed for {home_name} vs {away_name}: {e}")
            return None

    async def _get_rag_context(self, home: str, away: str) -> str:
        """Get historical context from RAG for match."""
        try:
            from core.rag import RAGEngine
            rag = RAGEngine()
            results = await rag.search(
                query=f"{home} {away} resultado histórico",
                collection="hedge_history",
                top_k=3,
                threshold=0.5,
            )
            if results:
                return " | ".join(
                    r.get("content", "")[:100] for r in results
                )
        except Exception:
            pass
        return ""

    async def _index_recommendations_to_rag(self, pipeline_data: dict) -> None:
        """Index recommendations into RAG for future backtesting."""
        try:
            from core.rag import RAGEngine
            rag = RAGEngine()
            for rec_dict in pipeline_data.get("recommendations", []):
                content = (
                    f"{rec_dict['home_team']} vs {rec_dict['away_team']} "
                    f"| {rec_dict['market']} | odd {rec_dict['decimal_odd']} "
                    f"| edge {rec_dict['edge']:.1%} | EV {rec_dict['expected_value']:.1%}"
                )
                await rag.ingest(
                    content=content,
                    metadata={
                        **rec_dict,
                        "type": "hedge_recommendation",
                        "outcome": None,        # filled when resolved
                        "date": pipeline_data["timestamp"],
                    },
                    collection="hedge_history",
                )
        except Exception as e:
            self.logger.debug(f"RAG indexing skipped: {e}")

    async def _send_telegram_report(
        self, recs: list, pipeline_data: dict
    ) -> None:
        """Send formatted bet recommendations via Telegram."""
        try:
            lines = [
                "🌙 *The Moon — Hedge Report*\n",
                f"📊 Analisados: {pipeline_data.get('total_analyzed', len(recs))} jogos",
                f"✅ APEX aprovados: {len(recs)}\n",
            ]
            for i, rec in enumerate(recs[:5], 1):
                star = (
                    "🔥" if rec.confidence == "high" else
                    "⚡" if rec.confidence == "medium" else "🔹"
                )
                lines.append(
                    f"{star} *{i}. {rec.home_team} vs {rec.away_team}*\n"
                    f"   Mercado: `{rec.market}` | Odd: `{rec.decimal_odd}`\n"
                    f"   Edge: `{rec.edge:.1%}` | EV: `{rec.expected_value:.1%}`\n"
                    f"   Stake: `{rec.stake_units:.1%}` "
                    f"({rec.confidence} confidence)\n"
                    f"   _{rec.reasoning}_\n"
                )

            # Bankroll summary
            lines.append(
                f"\n💰 Banca: `{self.kelly.bankroll:.2f}` "
                f"(DD: `{self.kelly._current_drawdown:.1%}`)"
            )

            from telegram.bot import send_notification
            await send_notification("\n".join(lines))
        except Exception as e:
            self.logger.debug(f"Telegram report skipped: {e}")

    def _load_or_create_engine(self, bankroll: float) -> KellyEngine:
        """Load persisted bankroll or create fresh engine."""
        state = self._load_bankroll_state()
        persisted = state.get("current_bankroll")
        if persisted and persisted > 0:
            engine = KellyEngine(bankroll=float(persisted))
            engine.initial_bankroll = float(
                state.get("initial_bankroll", bankroll)
            )
            return engine
        return KellyEngine(bankroll=bankroll)

    def _load_bankroll_state(self) -> dict:
        """Load bankroll state from JSON."""
        try:
            if self.BANKROLL_PATH.exists():
                return json.loads(self.BANKROLL_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_bankroll(self) -> None:
        """Persist bankroll state to JSON."""
        try:
            state = self._load_bankroll_state()
            history = state.get("history", [])
            history.append({
                "timestamp": datetime.now().isoformat(),
                "bankroll": self.kelly.bankroll,
                "drawdown": self.kelly._current_drawdown,
            })
            state.update({
                "current_bankroll": self.kelly.bankroll,
                "initial_bankroll": self.kelly.initial_bankroll,
                "history": history[-50:],   # keep last 50 entries
            })
            self.BANKROLL_PATH.write_text(
                json.dumps(state, indent=2), encoding="utf-8"
            )
        except Exception as e:
            self.logger.warning(f"Bankroll save failed: {e}")

    def _rec_to_dict(self, rec: BetRecommendation) -> dict:
        """Convert BetRecommendation to serializable dict."""
        return asdict(rec)

    def _dicts_to_recs(self, dicts: list) -> list:
        """Convert dicts back to BetRecommendation (approx)."""
        from dataclasses import fields
        valid_fields = {f.name for f in fields(BetRecommendation)}
        result = []
        for d in dicts:
            try:
                clean = {k: v for k, v in d.items() if k in valid_fields}
                result.append(BetRecommendation(**clean))
            except Exception:
                pass
        return result
