"""
tests/test_hive_integration.py
Testes para HiveIntegration — ponte entre Hive e Orchestrator.
Testes de integração real sem mocks excessivos.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.hive_integration import HiveIntegration


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.register_agent = MagicMock()
    return orch


@pytest.fixture
def integration(mock_orchestrator, mock_bus, mock_llm):
    return HiveIntegration(
        orchestrator=mock_orchestrator,
        bus=mock_bus,
        llm=mock_llm,
    )


# ── Instanciação ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instantiation(integration):
    assert integration._registered is False
    assert integration._started is False
    assert integration.hive is not None


# ── Register (teste simplificado sem patch) ─────────────────────

@pytest.mark.asyncio
async def test_register_registers_agents(integration, mock_orchestrator):
    """Testa que register() chama orchestrator.register_agent para cada agente."""
    # Mock dos agentes reais para evitar inicialização completa
    with patch("agents.scheduler_agent.SchedulerAgent") as mock_sa, \
         patch("agents.memory_agent.MemoryAgent") as mock_ma, \
         patch("agents.deep_web_research_agent.DeepWebResearchAgent") as mock_ra, \
         patch("agents.data_pipeline_agent.DataPipelineAgent") as mock_pa, \
         patch("agents.desktop_control_agent.DesktopControlAgent") as mock_da:
        
        # Configurar mocks
        for m in [mock_sa, mock_ma, mock_ra, mock_pa, mock_da]:
            m.return_value = MagicMock(_execute=AsyncMock())
        
        await integration.register()
        
        assert integration._registered is True
        assert len(integration.hive._agents) == 5
        assert mock_orchestrator.register_agent.call_count == 5


@pytest.mark.asyncio
async def test_register_idempotent(integration, mock_orchestrator):
    """Testa que register() é idempotente."""
    with patch("agents.scheduler_agent.SchedulerAgent") as mock_sa, \
         patch("agents.memory_agent.MemoryAgent") as mock_ma, \
         patch("agents.deep_web_research_agent.DeepWebResearchAgent") as mock_ra, \
         patch("agents.data_pipeline_agent.DataPipelineAgent") as mock_pa, \
         patch("agents.desktop_control_agent.DesktopControlAgent") as mock_da:
        
        for m in [mock_sa, mock_ma, mock_ra, mock_pa, mock_da]:
            m.return_value = MagicMock(_execute=AsyncMock())
        
        await integration.register()
        await integration.register()
        
        # Deve registrar apenas uma vez
        assert mock_orchestrator.register_agent.call_count == 5


# ── Start ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_calls_hive_start(integration):
    """Testa que start() chama hive.start()."""
    with patch("agents.scheduler_agent.SchedulerAgent") as mock_sa, \
         patch("agents.memory_agent.MemoryAgent") as mock_ma, \
         patch("agents.deep_web_research_agent.DeepWebResearchAgent") as mock_ra, \
         patch("agents.data_pipeline_agent.DataPipelineAgent") as mock_pa, \
         patch("agents.desktop_control_agent.DesktopControlAgent") as mock_da:
        
        for m in [mock_sa, mock_ma, mock_ra, mock_pa, mock_da]:
            m.return_value = MagicMock(_execute=AsyncMock())
        
        # Mock do hive.start
        integration._hive.start = AsyncMock()
        
        await integration.start()
        
        integration._hive.start.assert_called_once()
        assert integration._started is True


@pytest.mark.asyncio
async def test_start_idempotent(integration):
    """Testa que start() é idempotente."""
    with patch("agents.scheduler_agent.SchedulerAgent") as mock_sa, \
         patch("agents.memory_agent.MemoryAgent") as mock_ma, \
         patch("agents.deep_web_research_agent.DeepWebResearchAgent") as mock_ra, \
         patch("agents.data_pipeline_agent.DataPipelineAgent") as mock_pa, \
         patch("agents.desktop_control_agent.DesktopControlAgent") as mock_da:
        
        for m in [mock_sa, mock_ma, mock_ra, mock_pa, mock_da]:
            m.return_value = MagicMock(_execute=AsyncMock())
        
        integration._hive.start = AsyncMock()
        
        await integration.start()
        await integration.start()
        
        integration._hive.start.assert_called_once()


@pytest.mark.asyncio
async def test_start_auto_registers_if_needed(integration):
    """Testa que start() auto-registra se necessário."""
    with patch("agents.scheduler_agent.SchedulerAgent") as mock_sa, \
         patch("agents.memory_agent.MemoryAgent") as mock_ma, \
         patch("agents.deep_web_research_agent.DeepWebResearchAgent") as mock_ra, \
         patch("agents.data_pipeline_agent.DataPipelineAgent") as mock_pa, \
         patch("agents.desktop_control_agent.DesktopControlAgent") as mock_da:
        
        for m in [mock_sa, mock_ma, mock_ra, mock_pa, mock_da]:
            m.return_value = MagicMock(_execute=AsyncMock())
        
        assert integration._registered is False
        await integration.start()
        assert integration._registered is True


# ── Stop ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_calls_hive_stop(integration):
    """Testa que stop() chama hive.stop()."""
    integration._hive.stop = AsyncMock()
    integration._started = True
    await integration.stop()
    integration._hive.stop.assert_called_once()
    assert integration._started is False


@pytest.mark.asyncio
async def test_stop_not_started_is_safe(integration):
    """Testa que stop() é seguro se não started."""
    integration._hive.stop = AsyncMock()
    await integration.stop()
    integration._hive.stop.assert_not_called()


# ── Status ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_delegates_to_hive(integration):
    """Testa que status() delega para hive."""
    integration._hive.status = AsyncMock(return_value={
        "running": True, "agents_healthy": 5, "agents_total": 5
    })
    status = await integration.status()
    assert status["agents_healthy"] == 5
    integration._hive.status.assert_called_once()
