"""
tests/test_scheduler_agent.py
Tests for SchedulerAgent — Rainha da Colmeia.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from agents.scheduler_agent import SchedulerAgent
from core.agent_base import AgentPriority, TaskResult


@pytest.fixture
def mock_message_bus():
    """Mock MessageBus para testes."""
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=None)
    bus.subscribe = AsyncMock(return_value=None)
    return bus


@pytest.fixture
def agent():
    """Cria um SchedulerAgent com mocks."""
    with patch('agents.scheduler_agent.MessageBus') as MockBus, \
         patch('agents.scheduler_agent.AsyncScheduler') as MockScheduler:
        
        mock_bus_instance = MagicMock()
        mock_bus_instance.publish = AsyncMock(return_value=None)
        mock_bus_instance.subscribe = AsyncMock(return_value=None)
        MockBus.return_value = mock_bus_instance
        
        mock_scheduler_instance = AsyncMock()
        mock_scheduler_instance.__aenter__ = AsyncMock(return_value=mock_scheduler_instance)
        mock_scheduler_instance.__aexit__ = AsyncMock(return_value=None)
        mock_scheduler_instance.add_schedule = AsyncMock(return_value=None)
        mock_scheduler_instance.remove_schedule = AsyncMock(return_value=None)
        mock_scheduler_instance.start = AsyncMock(return_value=None)
        MockScheduler.return_value = mock_scheduler_instance
        
        agent = SchedulerAgent()
        agent._bus = mock_bus_instance
        agent._scheduler = mock_scheduler_instance
        return agent


@pytest.mark.asyncio
async def test_scheduler_agent_instantiation():
    """Testa que o SchedulerAgent é instanciado corretamente."""
    with patch('agents.scheduler_agent.MessageBus'), \
         patch('agents.scheduler_agent.AsyncScheduler'):
        agent = SchedulerAgent()
        assert agent.name == "SchedulerAgent"
        assert agent._registered_jobs == []
        assert agent._heartbeats == {}
        assert agent.priority == AgentPriority.MEDIUM


@pytest.mark.asyncio
async def test_initialize_registers_default_jobs(agent):
    """Testa que initialize() registra os jobs padrão."""
    await agent.initialize()
    assert agent.is_initialized is True
    assert len(agent._registered_jobs) == 3
    assert "health_check" in agent._registered_jobs
    assert "daily_research" in agent._registered_jobs
    assert "memory_sync" in agent._registered_jobs


@pytest.mark.asyncio
async def test_execute_list_jobs_empty(agent):
    """Testa list_jobs quando não há jobs."""
    agent._registered_jobs = []
    result = await agent._execute("list_jobs")
    assert result.success is True
    assert result.data["jobs"] == []


@pytest.mark.asyncio
async def test_execute_list_jobs_with_jobs(agent):
    """Testa list_jobs com jobs registrados."""
    agent._registered_jobs = ["job1", "job2", "job3"]
    result = await agent._execute("list_jobs")
    assert result.success is True
    assert result.data["jobs"] == ["job1", "job2", "job3"]


@pytest.mark.asyncio
async def test_execute_add_job(agent):
    """Testa adicionar um job cron dinamicamente."""
    result = await agent._execute(
        "add_job",
        job_id="test_job",
        cron_expr="0 8 * * *",
        topic="test.topic",
        payload={"key": "value"}
    )
    assert result.success is True
    assert result.data["job_id"] == "test_job"
    assert "test_job" in agent._registered_jobs


@pytest.mark.asyncio
async def test_execute_add_job_missing_params(agent):
    """Testa que add_job falha sem parâmetros necessários."""
    result = await agent._execute("add_job", job_id="test")
    assert result.success is False
    assert "requer" in result.error


@pytest.mark.asyncio
async def test_execute_remove_job(agent):
    """Testa remover um job."""
    agent._registered_jobs = ["job_to_remove"]
    result = await agent._execute("remove_job", job_id="job_to_remove")
    assert result.success is True
    assert result.data["removed"] == "job_to_remove"
    assert "job_to_remove" not in agent._registered_jobs


@pytest.mark.asyncio
async def test_execute_unknown_task(agent):
    """Testa que task desconhecida retorna erro."""
    result = await agent._execute("unknown_task")
    assert result.success is False
    assert "desconhecida" in result.error


@pytest.mark.asyncio
async def test_on_heartbeat_updates_dict(agent):
    """Testa que _on_heartbeat atualiza o dicionário de heartbeats."""
    await agent._on_heartbeat("MemoryAgent", {"status": "alive"})
    assert "MemoryAgent" in agent._heartbeats
    assert isinstance(agent._heartbeats["MemoryAgent"], datetime)


@pytest.mark.asyncio
async def test_on_heartbeat_wrapper(agent):
    """Testa o wrapper de heartbeat que recebe Message."""
    mock_message = MagicMock()
    mock_message.sender = "DeepWebResearchAgent"
    mock_message.payload = {"status": "running"}
    
    await agent._on_heartbeat_wrapper(mock_message)
    assert "DeepWebResearchAgent" in agent._heartbeats


@pytest.mark.asyncio
async def test_emit_health_check_publishes(agent, mock_message_bus):
    """Testa que _emit_health_check publica no tópico scheduler.tick."""
    agent._bus = mock_message_bus
    agent._heartbeats = {
        "MemoryAgent": datetime.now(timezone.utc),
        "OfflineAgent": datetime(2020, 1, 1, tzinfo=timezone.utc)
    }
    
    await agent._emit_health_check()
    
    assert mock_message_bus.publish.called
    call_args = mock_message_bus.publish.call_args
    assert call_args[0][1] == "scheduler.tick"
    payload = call_args[0][2]
    assert payload["event"] == "health_check"
    assert "OfflineAgent" in payload["offline_agents"]


@pytest.mark.asyncio
async def test_emit_daily_research_publishes(agent, mock_message_bus):
    """Testa que _emit_daily_research publica no tópico research.request."""
    agent._bus = mock_message_bus
    
    await agent._emit_daily_research()
    
    assert mock_message_bus.publish.called
    call_args = mock_message_bus.publish.call_args
    assert call_args[0][1] == "research.request"
    payload = call_args[0][2]
    assert "query" in payload
    assert "sources" in payload
    assert payload["depth"] == "deep"


@pytest.mark.asyncio
async def test_emit_memory_sync_publishes(agent, mock_message_bus):
    """Testa que _emit_memory_sync publica no tópico memory.store."""
    agent._bus = mock_message_bus
    
    await agent._emit_memory_sync()
    
    assert mock_message_bus.publish.called
    call_args = mock_message_bus.publish.call_args
    assert call_args[0][1] == "memory.store"
    payload = call_args[0][2]
    assert payload["event"] == "sync"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_add_cron_job_invalid_expression(agent):
    """Testa que cron expression inválido levanta erro."""
    with pytest.raises(ValueError, match="Cron expression inválido"):
        await agent.add_cron_job("bad_job", "invalid", "topic", {})


@pytest.mark.asyncio
async def test_scheduler_agent_priority():
    """Testa que o SchedulerAgent tem prioridade MEDIUM."""
    with patch('agents.scheduler_agent.MessageBus'), \
         patch('agents.scheduler_agent.AsyncScheduler'):
        agent = SchedulerAgent()
        assert agent.priority == AgentPriority.MEDIUM
