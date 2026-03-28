import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.autonomy_evolution_agent import AutonomyEvolutionAgent
from core.agent_base import TaskResult


@pytest.mark.asyncio
async def test_assess_generates_report_with_evidence(tmp_path, monkeypatch):
    jobs_file = tmp_path / "scheduled_jobs.json"
    flows_dir = tmp_path / "flows"
    templates_dir = tmp_path / "flow_templates"
    sessions_dir = tmp_path / "metrics" / "sessions"
    devops_dir = tmp_path / "devops_reports"
    sentinel_file = tmp_path / "sentinel_initiatives.json"
    output_dir = tmp_path / "autonomy"

    flows_dir.mkdir()
    templates_dir.mkdir()
    sessions_dir.mkdir(parents=True)
    devops_dir.mkdir()
    sentinel_file.write_text("[]", encoding="utf-8")
    (flows_dir / "existing_flow.json").write_text("{}", encoding="utf-8")

    jobs_file.write_text(
        """
{
  "jobs": [
    {"job_id": "ok-job", "flow_name": "existing_flow", "job_type": "flow", "enabled": true, "run_count": 2},
    {"job_id": "broken-job", "flow_name": "missing_flow", "job_type": "flow", "enabled": true, "run_count": 0}
  ]
}
        """.strip(),
        encoding="utf-8",
    )

    (sessions_dir / "session_1.json").write_text(
        f"""
{{
  "timestamp": {time.time() - 3600},
  "total_calls": 30,
  "total_errors": 6,
  "overall_success_rate": 0.8,
  "agents": {{
    "CrawlerAgent": {{"calls": 10, "success_rate": 0.6, "status": "degraded", "last_error": "timeout"}}
  }}
}}
        """.strip(),
        encoding="utf-8",
    )

    (devops_dir / "scan_20260328_010000.json").write_text(
        """
{
  "timestamp": "2026-03-28T01:00:00",
  "issues": [{"id": "a"}],
  "summary": {"critical": 1, "high": 0, "medium": 1, "low": 0}
}
        """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("GROQ_API_KEY", "ok")
    monkeypatch.setenv("GITHUB_TOKEN", "ok")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "ok")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    agent = AutonomyEvolutionAgent(orchestrator=None)
    agent.jobs_file = jobs_file
    agent.flows_dir = flows_dir
    agent.templates_dir = templates_dir
    agent.metrics_sessions_dir = sessions_dir
    agent.devops_reports_dir = devops_dir
    agent.sentinel_initiatives_file = sentinel_file
    agent.output_dir = output_dir

    result = await agent._execute("assess")
    assert result.success is True
    assert result.data["autonomy_score"] < 100
    assert result.data["limitations"]
    assert any(
        action["id"] == "fill_required_credentials"
        for action in result.data["assessment"]["recommended_actions"]
    )
    assert Path(result.data["report_path"]).exists()


@pytest.mark.asyncio
async def test_apply_next_steps_executes_automatable_actions(tmp_path, monkeypatch):
    orchestrator = MagicMock()
    orchestrator._call_agent = AsyncMock(return_value=TaskResult(success=True, data={"ok": True}))

    agent = AutonomyEvolutionAgent(orchestrator=orchestrator)
    agent.output_dir = tmp_path / "autonomy"
    agent.output_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        agent,
        "_generate_assessment",
        lambda: {
            "autonomy_score": 72.5,
            "recommended_actions": [
                {
                    "id": "run_devops_scan",
                    "priority": 90,
                    "title": "scan",
                    "rationale": "x",
                    "automated": True,
                    "command": "AutonomousDevOpsRefactor.run_scan",
                },
                {
                    "id": "trigger_skill_discovery",
                    "priority": 70,
                    "title": "discover",
                    "rationale": "x",
                    "automated": True,
                    "command": "SkillAlchemist.discover",
                },
                {
                    "id": "fill_required_credentials",
                    "priority": 100,
                    "title": "manual",
                    "rationale": "x",
                    "automated": False,
                    "command": "update env",
                },
            ],
        },
    )

    result = await agent._execute("apply_next_steps", top_n=2)
    assert result.success is True
    assert result.data["executed_actions"] == 2
    assert orchestrator._call_agent.await_count == 2

    called_agents = [call.args[0] for call in orchestrator._call_agent.await_args_list]
    assert called_agents == ["AutonomousDevOpsRefactor", "SkillAlchemist"]
