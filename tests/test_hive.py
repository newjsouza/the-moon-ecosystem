"""
tests/test_hive.py
Testes para HiveOrchestrator — coordenação dos 5 agentes da Colmeia.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.hive import Hive


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_llm():
    return AsyncMock()


def _make_mock_agent(name: str) -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.start = AsyncMock()
    from core.agent_base import TaskResult
    agent._execute = AsyncMock(
        return_value=TaskResult(success=True, data={"mock": name})
    )
    return agent


@pytest.fixture
def hive(mock_bus, mock_llm):
    return Hive(bus=mock_bus, llm=mock_llm)


@pytest.fixture
def started_hive(mock_bus, mock_llm):
    h = Hive(bus=mock_bus, llm=mock_llm)
    agents = {
        "SchedulerAgent":       _make_mock_agent("SchedulerAgent"),
        "MemoryAgent":          _make_mock_agent("MemoryAgent"),
        "DeepWebResearchAgent": _make_mock_agent("DeepWebResearchAgent"),
        "DataPipelineAgent":    _make_mock_agent("DataPipelineAgent"),
        "DesktopControlAgent":  _make_mock_agent("DesktopControlAgent"),
    }
    h._agents = agents
    h._running = True
    from datetime import datetime, timezone
    h._started_at = datetime.now(timezone.utc)
    return h


# ── Instanciação ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hive_instantiation(hive):
    assert hive._running is False
    assert hive._agents == {}
    assert hive._tasks == []
    assert hive._started_at is None


# ── Start ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hive_start_creates_all_agents(hive, mock_bus):
    agent_names = [
        "SchedulerAgent", "MemoryAgent", "DeepWebResearchAgent",
        "DataPipelineAgent", "DesktopControlAgent",
    ]
    mock_agents = {n: _make_mock_agent(n) for n in agent_names}

    with patch("core.hive.SchedulerAgent", return_value=mock_agents["SchedulerAgent"]), \
         patch("core.hive.MemoryAgent", return_value=mock_agents["MemoryAgent"]), \
         patch("core.hive.DeepWebResearchAgent",
               return_value=mock_agents["DeepWebResearchAgent"]), \
         patch("core.hive.DataPipelineAgent",
               return_value=mock_agents["DataPipelineAgent"]), \
         patch("core.hive.DesktopControlAgent",
               return_value=mock_agents["DesktopControlAgent"]):
        await hive.start()

    assert hive._running is True
    assert len(hive._agents) == 5
    for name in agent_names:
        assert name in hive._agents
    mock_bus.publish.assert_called_once()
    call = mock_bus.publish.call_args[0]
    assert call[1] == "hive.heartbeat"
    assert "hive_started" in call[2]["event"]


@pytest.mark.asyncio
async def test_hive_start_idempotent(started_hive, mock_bus):
    await started_hive.start()
    mock_bus.publish.assert_not_called()


# ── Stop ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hive_stop_calls_dp_close(started_hive):
    dp = started_hive._agents["DataPipelineAgent"]
    dp.close = AsyncMock()
    await started_hive.stop()
    dp.close.assert_called_once()
    assert started_hive._running is False


@pytest.mark.asyncio
async def test_hive_stop_not_running(hive):
    await hive.stop()
    assert hive._running is False


# ── Status ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hive_status_all_healthy(started_hive):
    status = await started_hive.status()
    assert status["running"] is True
    assert status["agents_total"] == 5
    assert status["agents_healthy"] == 5
    assert status["uptime_seconds"] is not None
    assert status["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_hive_status_partial_failure(started_hive):
    from core.agent_base import TaskResult
    started_hive._agents["MemoryAgent"]._execute = AsyncMock(
        return_value=TaskResult(success=False, error="not ready")
    )
    status = await started_hive.status()
    assert status["agents_healthy"] == 4
    assert status["agents"]["MemoryAgent"]["ok"] is False


@pytest.mark.asyncio
async def test_hive_status_timeout_handled(started_hive):
    async def slow_execute(task, **kwargs):
        await asyncio.sleep(10)
    started_hive._agents["DeepWebResearchAgent"]._execute = slow_execute
    status = await started_hive.status()
    assert status["agents"]["DeepWebResearchAgent"]["ok"] is False
    assert "timeout" in status["agents"]["DeepWebResearchAgent"]["data"]["error"]


# ── Propriedades de acesso ────────────────────────────────────────

@pytest.mark.asyncio
async def test_hive_properties_return_agents(started_hive):
    assert started_hive.scheduler.name == "SchedulerAgent"
    assert started_hive.memory.name == "MemoryAgent"
    assert started_hive.researcher.name == "DeepWebResearchAgent"
    assert started_hive.pipeline.name == "DataPipelineAgent"
    assert started_hive.desktop.name == "DesktopControlAgent"


@pytest.mark.asyncio
async def test_hive_get_agent_valid(started_hive):
    agent = started_hive.get_agent("MemoryAgent")
    assert agent.name == "MemoryAgent"


@pytest.mark.asyncio
async def test_hive_get_agent_invalid_raises(started_hive):
    with pytest.raises(KeyError) as exc_info:
        started_hive.get_agent("NonExistentAgent")
    assert "NonExistentAgent" in str(exc_info.value)
    assert "Disponíveis" in str(exc_info.value)
