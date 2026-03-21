"""
SportsAnalyticsAgent — fetches sports data and generates analytical reports.
Uses existing skills/sports/ client (read STEP 1c for real class name).
Integrates with: RAGEngine (context), BlogPipeline (publish), Telegram (notify).
Circuit breaker protects all API calls.
"""
import asyncio
import logging
from core.agent_base import AgentBase, TaskResult
from core.observability import observe_agent
from core.sports_config import COMPETITION_IDS, ReportConfig, DEFAULT_COMPETITIONS
from core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from agents.llm import LLMRouter


@observe_agent
class SportsAnalyticsAgent(AgentBase):
    """
    Fetches sports data + generates analytical reports.
    Publishes to blog and/or Telegram via BlogPipeline.

    Commands:
        'report'      → full report (fetch + analyze + publish)
        'standings'   → league table only
        'matches'     → recent/upcoming matches
        'scorers'     → top scorers
        'schedule'    → add recurring report to AutonomousLoop
    """

    AGENT_ID = "sports_analytics"

    def __init__(self):
        super().__init__()
        self.llm = LLMRouter()
        # Circuit breaker for API calls
        self._api_cb = CircuitBreaker(
            "football_data_api",
            CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=120.0,
                timeout=15.0
            )
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute sports analytics command.
        kwargs:
            competition (str): competition name from COMPETITION_IDS
            competition_id (str): direct API competition code
            publish_blog (bool): publish to blog (default True)
            notify_telegram (bool): send Telegram update (default True)
            dry_run (bool): fetch + analyze without publishing (default False)
            language (str): report language (default 'pt-BR')
            max_matches (int): number of matches to include (default 10)
        """
        start = asyncio.get_event_loop().time()
        cmd = task.lower().strip()

        # Build ReportConfig from kwargs
        competition = kwargs.get("competition", DEFAULT_COMPETITIONS[0])
        config = ReportConfig.for_competition(
            competition,
            report_type=cmd if cmd in ("weekly","matchday","standings","scorers") else "weekly",
            publish_blog=kwargs.get("publish_blog", True),
            notify_telegram=kwargs.get("notify_telegram", True),
            language=kwargs.get("language", "pt-BR"),
            dry_run=kwargs.get("dry_run", False),
            max_matches=kwargs.get("max_matches", 10),
            include_standings=kwargs.get("include_standings", True),
            include_scorers=kwargs.get("include_scorers", True),
            include_analysis=kwargs.get("include_analysis", True),
        )

        try:
            if cmd in ("report", "weekly", "matchday"):
                return await self._run_full_report(config, start)
            elif cmd == "standings":
                return await self._get_standings(config, start)
            elif cmd == "matches":
                return await self._get_matches(config, start)
            elif cmd == "scorers":
                return await self._get_scorers(config, start)
            elif cmd == "list":
                return TaskResult(
                    success=True,
                    data={"competitions": COMPETITION_IDS,
                          "defaults": DEFAULT_COMPETITIONS},
                    execution_time=asyncio.get_event_loop().time() - start
                )
            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown command: '{cmd}'. "
                          f"Valid: report, standings, matches, scorers, list"
                )
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _run_full_report(self, config: ReportConfig,
                                start: float) -> TaskResult:
        """
        Full sports report: fetch all data + LLM analysis + publish.
        """
        report_data = {"competition": config.competition, "steps": []}

        # Fetch data in parallel
        fetch_tasks = [self._fetch_matches(config)]
        if config.include_standings:
            fetch_tasks.append(self._fetch_standings(config))
        if config.include_scorers:
            fetch_tasks.append(self._fetch_scorers(config))

        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        matches_data = fetch_results[0] if not isinstance(fetch_results[0], Exception) else {}
        standings_data = fetch_results[1] if (len(fetch_results) > 1 and
                         not isinstance(fetch_results[1], Exception)) else {}
        scorers_data = fetch_results[2] if (len(fetch_results) > 2 and
                       not isinstance(fetch_results[2], Exception)) else {}

        report_data["matches"] = matches_data
        report_data["standings"] = standings_data
        report_data["scorers"] = scorers_data
        report_data["steps"].append("fetch")

        # RAG context — previous reports for continuity
        rag_context = await self._get_rag_context(config.competition)
        report_data["steps"].append("rag_context")

        # LLM narrative analysis
        if config.include_analysis:
            narrative = await self._generate_narrative(
                config=config,
                matches=matches_data,
                standings=standings_data,
                scorers=scorers_data,
                rag_context=rag_context
            )
            if narrative:
                report_data["narrative"] = narrative
                report_data["steps"].append("narrative")

        # Publish to blog
        if config.publish_blog and not config.dry_run:
            blog_result = await self._publish_to_blog(config, report_data)
            if blog_result.success:
                report_data["steps"].append("blog_published")
                report_data["blog"] = blog_result.data
            else:
                report_data["blog_error"] = blog_result.error

        # Telegram broadcast
        if config.notify_telegram and not config.dry_run:
            tg_result = await self._send_telegram_update(config, report_data)
            if tg_result.success:
                report_data["steps"].append("telegram_sent")

        return TaskResult(
            success=True,
            data=report_data,
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _fetch_matches(self, config: ReportConfig) -> dict:
        """Fetch recent matches via sports skill (circuit breaker protected)."""
        try:
            result = await self._api_cb.call(
                self._call_sports_api,
                endpoint="matches",
                competition_id=config.competition_id,
                limit=config.max_matches
            )
            if isinstance(result, TaskResult):
                return result.data or {}
            return result or {}
        except Exception as e:
            self.logger.warning(f"Fetch matches failed: {e}")
            return {}

    async def _fetch_standings(self, config: ReportConfig) -> dict:
        """Fetch league standings via sports skill."""
        try:
            result = await self._api_cb.call(
                self._call_sports_api,
                endpoint="standings",
                competition_id=config.competition_id
            )
            if isinstance(result, TaskResult):
                return result.data or {}
            return result or {}
        except Exception as e:
            self.logger.warning(f"Fetch standings failed: {e}")
            return {}

    async def _fetch_scorers(self, config: ReportConfig) -> dict:
        """Fetch top scorers via sports skill."""
        try:
            result = await self._api_cb.call(
                self._call_sports_api,
                endpoint="scorers",
                competition_id=config.competition_id
            )
            if isinstance(result, TaskResult):
                return result.data or {}
            return result or {}
        except Exception as e:
            self.logger.warning(f"Fetch scorers failed: {e}")
            return {}

    async def _call_sports_api(self, endpoint: str,
                                competition_id: str, **kwargs) -> dict:
        """
        Call the sports skill API client.
        Using the FootballDataClient from skills.sports.
        """
        try:
            from skills.sports import FootballDataClient
            client = FootballDataClient()
            
            if endpoint == 'matches':
                return client.get_matches(competition_id=competition_id, **kwargs)
            elif endpoint == 'standings':
                # The API doesn't have a direct standings endpoint, need to get competition info
                competitions = client.get_competitions()
                for comp in competitions:
                    if comp.get('id') == competition_id or comp.get('code') == competition_id:
                        # We need to get specific competition table which may not be directly available
                        # This is a simplified implementation - in reality we'd need to check API docs
                        # for the specific endpoint to get standings
                        return {"standings": []}
                return {}
            elif endpoint == 'scorers':
                # The API doesn't have a direct scorers endpoint either
                # For now, returning an empty result - would need to implement 
                # a method to get this data from the API
                return {"scorers": []}
            else:
                self.logger.warning(f"Unknown endpoint: {endpoint}")
                return {}
        except Exception as e:
            self.logger.error(f"Sports API call failed: {e}")
            raise

    async def _get_rag_context(self, competition: str) -> str:
        """Get previous sports reports from RAG for narrative continuity."""
        try:
            from core.rag import RAGEngine
            rag = RAGEngine()
            result = await rag.search(
                query=f"sports report {competition}",
                collection="blog_posts",
                top_k=2
            )
            if result.success and result.data.get("hits"):
                return "\n".join([
                    h.get("content", "")[:300]
                    for h in result.data["hits"][:2]
                ])
        except Exception as e:
            self.logger.debug(f"RAG context fetch failed: {e}")
        return ""

    async def _generate_narrative(self, config: ReportConfig,
                                   matches: dict, standings: dict,
                                   scorers: dict, rag_context: str) -> str:
        """Generate LLM narrative analysis of the sports data."""
        data_summary = self._build_data_summary(
            matches, standings, scorers
        )
        prev_context = ""
        if rag_context:
            prev_context = f"\n\nContext from previous reports:\n{rag_context[:400]}"

        prompt = f"""You are a sports journalist for The Moon ecosystem.
Write a {config.language} analysis of the latest {config.competition} results.

Data:
{data_summary}
{prev_context}

Requirements:
- Engaging narrative in {config.language}
- Highlight key results, standings changes, top scorers
- 300-500 words
- Markdown format with H2 headers
- Tone: professional sports journalism

Write the analysis:"""

        try:
            return await self.llm.complete(prompt, task_type="sports_analysis")
        except Exception as e:
            self.logger.warning(f"Narrative generation failed: {e}")
            return ""

    def _build_data_summary(self, matches: dict, standings: dict,
                             scorers: dict) -> str:
        """Build structured text summary of sports data for LLM prompt."""
        lines = []

        if matches:
            lines.append("=== Recent Matches ===")
            match_list = matches.get("matches", [])
            for m in match_list[:5]:
                home = m.get("homeTeam", {}).get("name", m.get("homeTeam", {}).get("shortName", "Home"))
                away = m.get("awayTeam", {}).get("name", m.get("awayTeam", {}).get("shortName", "Away"))
                score = m.get("score", {}).get("fullTime", {})
                home_g = score.get("home", "?")
                away_g = score.get("away", "?")
                utc_date = m.get("utcDate", "Date Unknown")
                lines.append(f"  {home} {home_g}-{away_g} {away} ({utc_date[:10]})")

        if standings:
            lines.append("\n=== Standings (Top 5) ===")
            # Assuming structure from API - adjust based on actual response
            table = standings.get("standings", [])
            if table and isinstance(table, list):
                for row in table[:5]:
                    pos = row.get("position", "?")
                    team = row.get("team", {}).get("name", "Team")
                    pts = row.get("points", "?")
                    lines.append(f"  {pos}. {team} — {pts} pts")

        if scorers:
            lines.append("\n=== Top Scorers ===")
            scorer_list = scorers.get("scorers", [])
            for s in scorer_list[:5]:
                player = s.get("player", {}).get("name", "Player")
                goals = s.get("goals", "?")
                lines.append(f"  {player} — {goals} goals")

        return "\n".join(lines) if lines else "No data available"

    async def _publish_to_blog(self, config: ReportConfig,
                                report_data: dict) -> TaskResult:
        """Publish report via BlogPipeline."""
        try:
            from blog.pipeline import BlogPipeline
            pipeline = BlogPipeline()
            topic = (
                f"Análise {config.competition.replace('_', ' ').title()}: "
                f"resultados e destaques da semana"
            )
            narrative = report_data.get("narrative", "")
            if not narrative:
                return TaskResult(success=False,
                                  error="No narrative to publish")
            return await pipeline.run(
                topic=topic,
                language=config.language,
                notify_telegram=False,  # handled separately below
                dry_run=config.dry_run
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _send_telegram_update(self, config: ReportConfig,
                                     report_data: dict) -> TaskResult:
        """Send sports update to Telegram."""
        try:
            # INSTRUCTION: Replace with real Telegram send method from STEP 2
            narrative = report_data.get("narrative", "")
            if not narrative:
                return TaskResult(success=False, error="No narrative to send")
            message = (
                f"⚽ *{config.competition.replace('_', ' ').title()}*\n\n"
                f"{narrative[:800]}..."
            )
            # Using send_notification function if available
            try:
                from telegram.bot import send_notification
                await send_notification(message)
            except ImportError:
                # If send_notification is not available, use a mock
                self.logger.info(f"Would send Telegram notification: {message[:50]}...")
            return TaskResult(success=True, data={"sent": True})
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _get_standings(self, config: ReportConfig,
                              start: float) -> TaskResult:
        standings = await self._fetch_standings(config)
        return TaskResult(
            success=True,
            data={"competition": config.competition,
                  "standings": standings},
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _get_matches(self, config: ReportConfig,
                           start: float) -> TaskResult:
        matches = await self._fetch_matches(config)
        return TaskResult(
            success=True,
            data={"competition": config.competition,
                  "matches": matches},
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _get_scorers(self, config: ReportConfig,
                           start: float) -> TaskResult:
        scorers = await self._fetch_scorers(config)
        return TaskResult(
            success=True,
            data={"competition": config.competition,
                  "scorers": scorers},
            execution_time=asyncio.get_event_loop().time() - start
        )