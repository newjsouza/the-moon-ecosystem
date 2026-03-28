from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.autonomous_devops_refactor import AutonomousDevOpsRefactor
from core.agent_base import TaskResult


@pytest.mark.asyncio
async def test_execute_auto_fix_triggers_scan(monkeypatch):
    agent = AutonomousDevOpsRefactor(groq_client=None, message_bus=MagicMock())
    fake_scan_result = TaskResult(
        success=True,
        data={
            "report_path": "data/devops_reports/scan_x.json",
            "summary": {"critical": 0, "high": 0, "medium": 1, "low": 2},
        },
    )
    monkeypatch.setattr(agent, "_run_scan", AsyncMock(return_value=fake_scan_result))

    result = await agent._execute("auto_fix", issues=["circuit aberto"])

    assert result.success is True
    assert result.data["issues_received"] == 1
    agent._run_scan.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_report_includes_issues_found():
    bus = MagicMock()
    bus.publish = AsyncMock()
    agent = AutonomousDevOpsRefactor(groq_client=None, message_bus=bus)

    report = {
        "summary": {"critical": 1, "high": 2, "medium": 0, "low": 3},
        "issues": [{"id": "a"}, {"id": "b"}],
        "actions_taken": ["scan"],
        "report_path": "data/devops_reports/scan_test.json",
    }

    await agent._publish_report(report)

    assert bus.publish.await_count == 1
    args = bus.publish.await_args.args
    assert args[1] == "devops.scan_complete"
    assert args[2]["issues_found"] == 2
