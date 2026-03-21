"""Sprint I — Test suite for SportsAnalyticsAgent and SportsConfig."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# SportsConfig tests
# ─────────────────────────────────────────────
class TestSportsConfig:

    def test_competition_ids_not_empty(self):
        from core.sports_config import COMPETITION_IDS
        assert len(COMPETITION_IDS) >= 5

    def test_brasileirao_in_competitions(self):
        from core.sports_config import COMPETITION_IDS
        assert "brasileirao" in COMPETITION_IDS

    def test_champions_league_in_competitions(self):
        from core.sports_config import COMPETITION_IDS
        assert "champions_league" in COMPETITION_IDS

    def test_report_config_default(self):
        from core.sports_config import ReportConfig
        rc = ReportConfig()
        assert rc.competition == "brasileirao"
        assert rc.language == "pt-BR"
        assert rc.publish_blog is True

    def test_report_config_for_competition(self):
        from core.sports_config import ReportConfig
        rc = ReportConfig.for_competition("premier_league")
        assert rc.competition == "premier_league"
        assert rc.competition_id == "PL"

    def test_report_config_for_unknown_competition(self):
        from core.sports_config import ReportConfig
        rc = ReportConfig.for_competition("unknown_league")
        assert rc.competition == "unknown_league"
        assert len(rc.competition_id) > 0

    def test_default_competitions_valid(self):
        from core.sports_config import DEFAULT_COMPETITIONS, COMPETITION_IDS
        for comp in DEFAULT_COMPETITIONS:
            assert comp in COMPETITION_IDS

    def test_report_config_dry_run(self):
        from core.sports_config import ReportConfig
        rc = ReportConfig(dry_run=True)
        assert rc.dry_run is True


# ─────────────────────────────────────────────
# SportsAnalyticsAgent tests
# ─────────────────────────────────────────────
class TestSportsAnalyticsAgent:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        from agents.sports_analytics_agent import SportsAnalyticsAgent
        self.agent = SportsAnalyticsAgent()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_instantiation(self):
        assert self.agent.AGENT_ID == "sports_analytics"

    def test_execute_signature(self):
        import inspect
        sig = inspect.signature(self.agent._execute)
        assert 'task' in str(sig) and 'kwargs' in str(sig)

    def test_is_agent_base(self):
        from core.agent_base import AgentBase
        assert isinstance(self.agent, AgentBase)

    def test_circuit_breaker_created(self):
        from core.circuit_breaker import CircuitBreaker
        assert isinstance(self.agent._api_cb, CircuitBreaker)

    @pytest.mark.asyncio
    async def test_execute_list_command(self):
        result = await self.agent._execute("list")
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert "competitions" in result.data

    @pytest.mark.asyncio
    async def test_execute_unknown_command(self):
        result = await self.agent._execute("invalid_xyz")
        assert result.success is False
        assert "Unknown command" in result.error

    @pytest.mark.asyncio
    async def test_execute_standings_with_mock(self):
        mock_data = {"standings": [{"table": [
            {"position": 1, "team": {"name": "Flamengo"}, "points": 45}
        ]}]}
        with patch.object(self.agent, '_fetch_standings',
                          new_callable=AsyncMock, return_value=mock_data):
            result = await self.agent._execute(
                "standings", competition="brasileirao"
            )
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert "standings" in result.data

    @pytest.mark.asyncio
    async def test_execute_matches_with_mock(self):
        mock_data = {"matches": [
            {"homeTeam": {"name": "FLA"}, "awayTeam": {"name": "FLU"},
             "score": {"fullTime": {"home": 2, "away": 1}}}
        ]}
        with patch.object(self.agent, '_fetch_matches',
                          new_callable=AsyncMock, return_value=mock_data):
            result = await self.agent._execute(
                "matches", competition="brasileirao"
            )
        assert isinstance(result, TaskResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_scorers_with_mock(self):
        mock_data = {"scorers": [
            {"player": {"name": "Pedro"}, "goals": 15}
        ]}
        with patch.object(self.agent, '_fetch_scorers',
                          new_callable=AsyncMock, return_value=mock_data):
            result = await self.agent._execute(
                "scorers", competition="brasileirao"
            )
        assert isinstance(result, TaskResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_report_dry_run(self):
        mock_matches = {"matches": []}
        mock_standings = {"standings": [{"table": []}]}
        mock_scorers = {"scorers": []}
        mock_narrative = "Análise da rodada de futebol."

        with patch.object(self.agent, '_fetch_matches',
                          new_callable=AsyncMock, return_value=mock_matches), \
             patch.object(self.agent, '_fetch_standings',
                          new_callable=AsyncMock, return_value=mock_standings), \
             patch.object(self.agent, '_fetch_scorers',
                          new_callable=AsyncMock, return_value=mock_scorers), \
             patch.object(self.agent, '_generate_narrative',
                          new_callable=AsyncMock, return_value=mock_narrative), \
             patch.object(self.agent, '_get_rag_context',
                          new_callable=AsyncMock, return_value=""):
            result = await self.agent._execute(
                "report",
                competition="brasileirao",
                dry_run=True,
                notify_telegram=False,
                publish_blog=False
            )
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert "fetch" in result.data.get("steps", [])

    @pytest.mark.asyncio
    async def test_circuit_breaker_protects_api_call(self):
        """Simulate API failure cascade triggering circuit breaker."""
        from core.circuit_breaker import CircuitState
        for _ in range(3):
            self.agent._api_cb._on_failure()
        assert self.agent._api_cb.is_open
        # Now a fetch should return empty dict (CB blocks the call)
        from core.sports_config import ReportConfig
        config = ReportConfig()
        matches = await self.agent._fetch_matches(config)
        assert isinstance(matches, dict)  # returns {} on failure

    @pytest.mark.asyncio
    async def test_generate_narrative_calls_llm(self):
        from core.sports_config import ReportConfig
        config = ReportConfig()
        mock_narrative = "## Rodada 15\n\nFlamengo vence e assume a liderança."
        with patch.object(self.agent.llm, 'complete',
                          new_callable=AsyncMock, return_value=mock_narrative):
            result = await self.agent._generate_narrative(
                config=config,
                matches={"matches": []},
                standings={},
                scorers={},
                rag_context=""
            )
        assert result == mock_narrative

    def test_build_data_summary_with_data(self):
        matches = {"matches": [
            {"homeTeam": {"name": "FLA"}, "awayTeam": {"name": "FLU"},
             "score": {"fullTime": {"home": 2, "away": 1}},
             "utcDate": "2026-03-20T20:00:00Z"}
        ]}
        standings = {"standings": [
            {"position": 1, "team": {"name": "Flamengo"}, "points": 45}
        ]}
        scorers = {"scorers": [{"player": {"name": "Pedro"}, "goals": 15}]}
        summary = self.agent._build_data_summary(matches, standings, scorers)
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "FLA" in summary or "FLU" in summary

    def test_build_data_summary_empty(self):
        summary = self.agent._build_data_summary({}, {}, {})
        assert "No data available" in summary

    @pytest.mark.asyncio
    async def test_get_rag_context_graceful_failure(self):
        with patch('core.rag.RAGEngine.search',
                   side_effect=Exception("RAG unavailable")):
            context = await self.agent._get_rag_context("brasileirao")
        assert context == ""

    @pytest.mark.asyncio
    async def test_publish_to_blog_dry_run(self):
        from core.sports_config import ReportConfig
        config = ReportConfig(dry_run=True)
        report_data = {"narrative": "Test narrative " * 20}
        with patch('blog.pipeline.BlogPipeline.run',
                   new_callable=AsyncMock,
                   return_value=TaskResult(success=True, data={"dry_run": True})):
            result = await self.agent._publish_to_blog(config, report_data)
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_publish_to_blog_no_narrative_fails(self):
        from core.sports_config import ReportConfig
        config = ReportConfig()
        result = await self.agent._publish_to_blog(config, {})
        assert result.success is False
        assert "narrative" in result.error.lower()

    def test_has_observe_agent_decorator(self):
        with open('agents/sports_analytics_agent.py') as f:
            content = f.read()
        assert '@observe_agent' in content


# ─────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────
class TestSprintIIntegration:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_all_imports(self):
        from agents.sports_analytics_agent import SportsAnalyticsAgent
        from core.sports_config import COMPETITION_IDS, ReportConfig
        assert all([SportsAnalyticsAgent, COMPETITION_IDS, ReportConfig])

    def test_agent_base_compliance(self):
        from agents.sports_analytics_agent import SportsAnalyticsAgent
        from core.agent_base import AgentBase
        assert issubclass(SportsAnalyticsAgent, AgentBase)

    def test_script_syntax(self):
        import ast
        ast.parse(open('scripts/run_sports_report.py').read())

    def test_loop_task_for_sports(self):
        from core.loop_task import LoopTask
        from core.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        task = LoopTask(
            agent_id="sports_analytics",
            task="report",
            kwargs={"competition": "brasileirao", "dry_run": True},
            priority=4,
            domain="general"
        )
        loop.enqueue(task)
        assert loop.queue_size() == 1

    @pytest.mark.asyncio
    async def test_end_to_end_via_loop_mock(self):
        from core.autonomous_loop import AutonomousLoop
        from core.loop_task import LoopTask

        loop = AutonomousLoop()
        mock_orch = MagicMock()
        mock_orch._call_agent = AsyncMock(return_value=TaskResult(
            success=True,
            data={"steps": ["fetch", "narrative"],
                  "competition": "brasileirao"}
        ))
        loop.orchestrator = mock_orch

        task = LoopTask(
            agent_id="sports_analytics",
            task="report",
            kwargs={"competition": "brasileirao", "dry_run": True},
            use_evaluator=False
        )
        loop.enqueue(task)
        result = await loop.run(max_iterations=3, tick_interval=0.01)
        assert result.success is True
        assert result.data["completed"] >= 1