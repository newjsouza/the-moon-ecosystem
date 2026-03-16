"""
tests/test_main_bootstrap.py
Testes para bootstrap do sistema e ArchitectAgent como ponto de entrada.

Cobertura:
  - Import do main.py sem side effect destrutivo
  - Bootstrap bem-sucedido com dependências mockadas
  - Falha controlada de um subagente não crítico
  - Shutdown limpo
  - ArchitectAgent sendo efetivamente instanciado e iniciado
  - Signal handlers (SIGINT/SIGTERM)
"""
import pytest
import asyncio
import os
import signal
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_env():
    """Mock de variáveis de ambiente mínimas."""
    original_env = os.environ.copy()
    os.environ["GROQ_API_KEY"] = "test_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_orchestrator():
    """Mock do Orchestrator."""
    orchestrator = MagicMock()
    orchestrator.llm = AsyncMock()
    orchestrator.message_bus = MagicMock()
    orchestrator.message_bus.publish = AsyncMock()
    orchestrator.message_bus.subscribe = MagicMock()
    orchestrator.workspace_manager = MagicMock()
    orchestrator.workspace_manager.create_room = AsyncMock()
    orchestrator.register_agent = MagicMock()
    orchestrator.register_channel = MagicMock()
    orchestrator.start = AsyncMock()
    orchestrator.stop = AsyncMock()
    orchestrator.get_status = MagicMock(return_value={
        "agents_online": 5,
        "skills_online": 0,
        "channels_online": 0,
    })
    orchestrator._agent_instances = {}
    return orchestrator


# ─────────────────────────────────────────────────────────────
#  Testes de Import
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_main_import_without_side_effects():
    """Testa import do main.py sem side effects destrutivos."""
    # Import não deve levantar exceções
    from main import (
        MoonSystem,
        bootstrap_system,
        setup_logging,
        validate_environment,
        run,
    )
    
    assert MoonSystem is not None
    assert bootstrap_system is not None
    assert setup_logging is not None
    assert validate_environment is not None


@pytest.mark.unit
def test_moonsystem_class_exists():
    """Testa que MoonSystem class existe."""
    from main import MoonSystem
    
    assert hasattr(MoonSystem, "__init__")
    assert hasattr(MoonSystem, "start")
    assert hasattr(MoonSystem, "stop")
    assert hasattr(MoonSystem, "execute")
    assert hasattr(MoonSystem, "get_status")


# ─────────────────────────────────────────────────────────────
#  Testes de validate_environment()
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_validate_environment_with_groq(mock_env):
    """Testa validação de ambiente com Groq configurado."""
    from main import validate_environment
    
    status = validate_environment()
    
    assert status["groq_available"] is True
    assert status["llm_configured"] is True


@pytest.mark.unit
def test_validate_environment_no_providers(env_cleanup):
    """Testa validação sem nenhum provider."""
    from main import validate_environment
    
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    status = validate_environment()
    
    assert status["groq_available"] is False
    assert status["llm_configured"] is False


# ─────────────────────────────────────────────────────────────
#  Testes de MoonSystem
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_moonsystem_initialization():
    """Testa inicialização básica do MoonSystem."""
    from main import MoonSystem
    
    system = MoonSystem()
    
    assert system.config is not None
    assert system.orchestrator is not None
    assert system.architect is None  # Ainda não inicializado
    assert system._initialized is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moonsystem_bootstrap_core_agents(mock_orchestrator):
    """Testa bootstrap de agentes core."""
    from main import MoonSystem

    with patch('main.Orchestrator', return_value=mock_orchestrator):
        system = MoonSystem()
        system.orchestrator = mock_orchestrator

        # Mock dos agentes core (import direto dos módulos)
        with patch('agents.watchdog.WatchdogAgent') as mock_watchdog, \
             patch('agents.llm.LlmAgent') as mock_llm, \
             patch('agents.terminal.TerminalAgent') as mock_terminal, \
             patch('agents.file_manager.FileManagerAgent') as mock_file_manager:

            mock_watchdog.return_value = MagicMock()
            mock_llm.return_value = MagicMock()
            mock_terminal.return_value = MagicMock()
            mock_file_manager.return_value = MagicMock()

            # Não deve levantar exceções
            await system._bootstrap_core_agents()

            # Verifica que agentes foram registrados
            assert mock_orchestrator.register_agent.call_count >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moonsystem_bootstrap_architect(mock_orchestrator):
    """Testa bootstrap do ArchitectAgent."""
    from main import MoonSystem
    from agents.architect import ArchitectAgent

    mock_architect = MagicMock(spec=ArchitectAgent)
    mock_architect.initialize = AsyncMock()

    with patch('main.Orchestrator', return_value=mock_orchestrator), \
         patch('agents.architect.ArchitectAgent', return_value=mock_architect):

        system = MoonSystem()
        system.orchestrator = mock_orchestrator

        await system._bootstrap_architect()

        # Verifica que Architect foi inicializado
        assert mock_architect.initialize.called
        assert system.architect is not None
        assert "ArchitectAgent" in mock_orchestrator._agent_instances


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moonsystem_graceful_degradation(mock_orchestrator):
    """Testa que falha em agente não crítico não mata o sistema."""
    from main import MoonSystem
    
    with patch('main.Orchestrator', return_value=mock_orchestrator):
        system = MoonSystem()
        system.orchestrator = mock_orchestrator
        
        # Mock que falha para um agente
        def safe_import_agent(module_path, class_name, **kwargs):
            if module_path == "agents.non_existent":
                return None
            return MagicMock()
        
        system._safe_import_agent = safe_import_agent
        
        # Não deve levantar exceções mesmo com agente falhando
        await system._bootstrap_specialized_agents()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moonsystem_start(mock_orchestrator):
    """Testa start do sistema."""
    from main import MoonSystem
    
    with patch('main.Orchestrator', return_value=mock_orchestrator):
        system = MoonSystem()
        system.orchestrator = mock_orchestrator
        
        await system.start()
        
        assert system._initialized is True
        assert mock_orchestrator.start.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moonsystem_stop(mock_orchestrator):
    """Testa stop do sistema."""
    from main import MoonSystem
    
    with patch('main.Orchestrator', return_value=mock_orchestrator):
        system = MoonSystem()
        system.orchestrator = mock_orchestrator
        
        # Mock architect
        mock_architect = MagicMock()
        mock_architect.shutdown = AsyncMock()
        system.architect = mock_architect
        
        await system.stop()
        
        assert mock_orchestrator.stop.called
        assert mock_architect.shutdown.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moonsystem_get_status(mock_orchestrator):
    """Testa obtenção de status do sistema."""
    from main import MoonSystem
    
    with patch('main.Orchestrator', return_value=mock_orchestrator):
        system = MoonSystem()
        system.orchestrator = mock_orchestrator
        
        status = system.get_status()
        
        assert isinstance(status, dict)
        assert "agents_online" in status


# ─────────────────────────────────────────────────────────────
#  Testes de Bootstrap System
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_system_success():
    """Testa bootstrap completo do sistema."""
    from main import bootstrap_system

    mock_orchestrator = MagicMock()
    mock_orchestrator.llm = AsyncMock()
    mock_orchestrator.message_bus = MagicMock()
    mock_orchestrator.message_bus.publish = AsyncMock()
    mock_orchestrator.message_bus.subscribe = MagicMock()
    mock_orchestrator.workspace_manager = MagicMock()
    mock_orchestrator.workspace_manager.create_room = AsyncMock()
    mock_orchestrator.register_agent = MagicMock()
    mock_orchestrator.register_channel = MagicMock()
    mock_orchestrator.start = AsyncMock()
    mock_orchestrator.stop = AsyncMock()
    mock_orchestrator.get_status = MagicMock(return_value={})
    mock_orchestrator._agent_instances = {}

    mock_architect = MagicMock()
    mock_architect.initialize = AsyncMock()
    mock_architect.shutdown = AsyncMock()
    mock_architect.register_agent = AsyncMock()

    with patch('main.Orchestrator', return_value=mock_orchestrator), \
         patch('agents.architect.ArchitectAgent', return_value=mock_architect), \
         patch('agents.watchdog.WatchdogAgent', return_value=MagicMock()), \
         patch('agents.llm.LlmAgent', return_value=MagicMock()), \
         patch('agents.terminal.TerminalAgent', return_value=MagicMock()), \
         patch('agents.file_manager.FileManagerAgent', return_value=MagicMock()):

        system = await bootstrap_system()

        assert system is not None
        assert system.architect is not None


# ─────────────────────────────────────────────────────────────
#  Testes de Signal Handlers
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_setup_signal_handlers():
    """Testa setup de signal handlers."""
    from main import setup_signal_handlers, MoonSystem
    
    mock_system = MagicMock(spec=MoonSystem)
    
    # Não deve levantar exceções
    setup_signal_handlers(mock_system)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_graceful_shutdown():
    """Testa shutdown limpo."""
    from main import _graceful_shutdown, MoonSystem
    
    mock_system = MagicMock(spec=MoonSystem)
    mock_system.stop = AsyncMock()
    mock_system._initialized = True
    
    await _graceful_shutdown(mock_system)
    
    assert mock_system.stop.called


# ─────────────────────────────────────────────────────────────
#  Testes de ArchitectAgent como Coordenador
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_architect_is_central_coordinator(mock_orchestrator):
    """Testa que ArchitectAgent é o coordenador central."""
    from main import MoonSystem
    from agents.architect import ArchitectAgent

    with patch('main.Orchestrator', return_value=mock_orchestrator), \
         patch('agents.architect.ArchitectAgent') as mock_architect_class:

        mock_architect = MagicMock(spec=ArchitectAgent)
        mock_architect.initialize = AsyncMock()
        mock_architect.register_agent = AsyncMock()
        mock_architect_class.return_value = mock_architect

        system = MoonSystem()
        system.orchestrator = mock_orchestrator

        await system._bootstrap_architect()

        # Verifica que Architect foi registrado no orchestrator
        assert mock_orchestrator.register_agent.called
        assert "ArchitectAgent" in mock_orchestrator._agent_instances

        # Verifica que Architect está acessível
        assert system.architect is not None


# ─────────────────────────────────────────────────────────────
#  Testes de Snake Case Conversion
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_to_snake_case():
    """Testa conversão para snake_case."""
    from main import MoonSystem
    
    assert MoonSystem._to_snake_case("ArchitectAgent") == "architect_agent"
    assert MoonSystem._to_snake_case("EconomicSentinel") == "economic_sentinel"
    assert MoonSystem._to_snake_case("LLMAgent") == "llm_agent"
    assert MoonSystem._to_snake_case("SimpleAgent") == "simple_agent"


# ─────────────────────────────────────────────────────────────
#  Testes de Safe Import Agent
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_safe_import_agent_success():
    """Testa import seguro de agente que existe."""
    from main import MoonSystem
    
    system = MoonSystem()
    
    # Tenta importar agente que existe
    agent = system._safe_import_agent(
        "agents.watchdog",
        "WatchdogAgent",
        message_bus=MagicMock()
    )
    
    assert agent is not None


@pytest.mark.unit
def test_safe_import_agent_not_found():
    """Testa import seguro de agente que não existe."""
    from main import MoonSystem
    
    system = MoonSystem()
    
    # Tenta importar agente que não existe
    agent = system._safe_import_agent(
        "agents.non_existent_module",
        "NonExistentAgent"
    )
    
    assert agent is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
