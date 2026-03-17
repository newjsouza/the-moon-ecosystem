"""
tests/test_watchdog.py
Testes para WatchdogAgent (Guardião do Sistema).

Cobertura:
  - Allowlist/blocklist de modelos
  - Detecção de uso de modelo proibido
  - Cálculo de custo acumulado
  - Cooldown/deduplicação de alertas
  - Comportamento quando CPU/RAM/disco excedem limites
  - Fallback de leitura de recursos do sistema
"""
import pytest
import os
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agents.watchdog import (
    WatchdogAgent,
    _ALLOWED_MODEL_PATTERNS,
    _BLOCKED_MODEL_PATTERNS,
    MONITOR_INTERVAL,
    ALERT_COOLDOWN,
)
from core.agent_base import TaskResult


# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def watchdog():
    """Cria instância do WatchdogAgent para testes."""
    return WatchdogAgent()


@pytest.fixture
def watchdog_with_message_bus(mock_message_bus):
    """Cria WatchdogAgent com MessageBus mockado."""
    return WatchdogAgent(message_bus=mock_message_bus)


# ─────────────────────────────────────────────────────────────
#  Testes de Import e Inicialização
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
def test_watchdog_import():
    """Teste básico de import do WatchdogAgent."""
    from agents.watchdog import WatchdogAgent
    assert WatchdogAgent is not None


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_watchdog_initialize(watchdog):
    """Testa inicialização do WatchdogAgent."""
    await watchdog.initialize()
    assert watchdog._monitoring_task is not None
    assert not watchdog._stop_event.is_set()
    await watchdog.shutdown()


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_watchdog_shutdown(watchdog):
    """Testa shutdown limpo do WatchdogAgent."""
    await watchdog.initialize()
    await watchdog.shutdown()
    assert watchdog._stop_event.is_set()


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_watchdog_ping(watchdog):
    """Testa liveness probe do WatchdogAgent."""
    await watchdog.initialize()
    result = await watchdog.ping()
    assert result is True
    await watchdog.shutdown()


# ─────────────────────────────────────────────────────────────
#  Testes de Política de Custo (Allowlist/Blocklist)
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
def test_allowed_model_patterns(watchdog):
    """Testa modelos na allowlist."""
    allowed_models = [
        "llama-3.3-70b",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "mixtral-8x7b",
        "whisper-large-v3",
        "nemotron-3-super",
        "mistral-large",
        "opencode",
        "minimax-m2.5",
        "gpt-5-nano",
        "qwen-72b",
        "deepseek-67b",
        "phi-3",
        "falcon-180b",
        "bloom-7b",
    ]
    
    for model in allowed_models:
        result = watchdog._check_cost_policy(model)
        assert result.success is True, f"Modelo {model} deveria ser permitido"


@pytest.mark.unit
@pytest.mark.watchdog
def test_blocked_model_patterns(watchdog):
    """Testa modelos na blocklist (pagos)."""
    blocked_models = [
        "gpt-4-turbo",
        "gpt-4-32k",
        "gpt-3.5-turbo",
        "claude-3-opus",
        "claude-3-sonnet",
        "claude-3-haiku",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "text-davinci-003",
        "o1-preview",
        "o1-mini",
    ]
    
    for model in blocked_models:
        result = watchdog._check_cost_policy(model)
        assert result.success is False, f"Modelo {model} deveria ser bloqueado"
        assert "Cost Violation" in result.error or "blocked pattern" in result.error


@pytest.mark.unit
@pytest.mark.watchdog
def test_unknown_model_blocked(watchdog):
    """Testa que modelos desconhecidos são bloqueados por default."""
    unknown_models = [
        "modelo-misterioso-123",
        "paid-model-pro",
        "unknown-llm",
    ]
    
    for model in unknown_models:
        result = watchdog._check_cost_policy(model)
        assert result.success is False, f"Modelo desconhecido {model} deveria ser bloqueado"
        assert "allowlist" in result.error


@pytest.mark.unit
@pytest.mark.watchdog
def test_model_check_case_insensitive(watchdog):
    """Testa que verificação de modelos é case-insensitive."""
    result1 = watchdog._check_cost_policy("LLAMA-3.3-70B")
    result2 = watchdog._check_cost_policy("llama-3.3-70b")
    
    assert result1.success is True
    assert result2.success is True


# ─────────────────────────────────────────────────────────────
#  Testes de Registro de Custo
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
def test_record_zero_cost(watchdog):
    """Testa registro de custo zero (permitido)."""
    initial_cost = watchdog.total_cost_accumulated
    result = watchdog._record_cost(0.0, "llama-3.3-70b")
    
    assert result.success is True
    assert watchdog.total_cost_accumulated == initial_cost


@pytest.mark.unit
@pytest.mark.watchdog
def test_record_positive_cost_violation(watchdog):
    """Testa que custo positivo viola política de custo zero."""
    initial_cost = watchdog.total_cost_accumulated
    result = watchdog._record_cost(0.001, "gpt-4")
    
    assert result.success is False
    assert watchdog.total_cost_accumulated > initial_cost
    assert "VIOLATION" in result.error


@pytest.mark.unit
@pytest.mark.watchdog
def test_cost_accumulation(watchdog):
    """Testa acumulador de custo."""
    watchdog._record_cost(0.001, "model1")
    watchdog._record_cost(0.002, "model2")
    
    assert watchdog.total_cost_accumulated == 0.003


# ─────────────────────────────────────────────────────────────
#  Testes de Alertas e Deduplicação
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
def test_alert_deduplication(watchdog):
    """Testa que alertas não disparam em loop dentro do cooldown."""
    alert_key = "test_alert"
    message = "Test alert message"
    
    # Primeiro alerta deve disparar
    watchdog._fire_alert(alert_key, message)
    initial_history_len = len(watchdog._alert_history)
    
    # Segundo alerta dentro do cooldown não deve disparar
    watchdog._fire_alert(alert_key, message)
    assert len(watchdog._alert_history) == initial_history_len


@pytest.mark.unit
@pytest.mark.watchdog
def test_alert_after_cooldown(watchdog):
    """Testa que alerta dispara após cooldown."""
    alert_key = "test_alert_cooldown"
    message = "Test alert after cooldown"
    
    # Primeiro alerta
    watchdog._fire_alert(alert_key, message)
    initial_history_len = len(watchdog._alert_history)
    
    # Simula passagem do tempo (avança _alert_last_seen)
    watchdog._alert_last_seen[alert_key] = time.monotonic() - ALERT_COOLDOWN - 10
    
    # Segundo alerta após cooldown deve disparar
    watchdog._fire_alert(alert_key, message)
    assert len(watchdog._alert_history) > initial_history_len


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_alert_publishes_to_messagebus(watchdog_with_message_bus):
    """Testa que alertas são publicados na MessageBus."""
    await watchdog_with_message_bus.initialize()
    
    watchdog_with_message_bus._fire_alert("test", "Test alert")
    
    # Aguarda task assíncrona
    await asyncio.sleep(0.1)
    
    assert watchdog_with_message_bus._message_bus.publish.called
    await watchdog_with_message_bus.shutdown()


# ─────────────────────────────────────────────────────────────
#  Testes de Health Check
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_health_check_healthy(watchdog):
    """Testa health check quando sistema está saudável."""
    # Define limites em 100% (impossível de exceder) para garantir zero alertas
    watchdog.max_cpu_percent = 100.0
    watchdog.max_memory_percent = 100.0
    watchdog.max_disk_usage_percent = 100.0

    issues = await watchdog._perform_health_check()
    assert len(issues) == 0


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_health_check_cpu_high(watchdog):
    """Testa health check com CPU alta."""
    # Mock _get_system_status para simular CPU alta
    async def mock_status():
        return {
            "cpu_percent": 95.0,  # CPU alta
            "memory_percent": 50.0,
            "disk_usage_percent": 50.0,
            "process_count": 100,
            "uptime_seconds": 3600,
            "cost_policy": "Zero Cost",
            "accumulated_cost": 0.0,
            "alert_count": 0,
        }

    watchdog._get_system_status = mock_status
    watchdog.max_cpu_percent = 85.0  # Limite normal

    issues = await watchdog._perform_health_check()
    assert any("CPU" in issue for issue in issues)


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_health_check_cost_violation(watchdog):
    """Testa health check com violação de custo."""
    watchdog._record_cost(0.001, "gpt-4")
    
    issues = await watchdog._perform_health_check()
    assert any("COST" in issue or "cost" in issue for issue in issues)


# ─────────────────────────────────────────────────────────────
#  Testes de Métricas do Sistema
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_get_system_status(watchdog):
    """Testa coleta de métricas do sistema."""
    status = await watchdog._get_system_status()
    
    assert "cpu_percent" in status
    assert "memory_percent" in status
    assert "disk_usage_percent" in status
    assert "process_count" in status
    assert "uptime_seconds" in status
    assert "cost_policy" in status
    assert "accumulated_cost" in status


@pytest.mark.unit
@pytest.mark.watchdog
def test_cpu_fallback():
    """Testa fallback de leitura de CPU via /proc."""
    from agents.watchdog import WatchdogAgent
    import os
    
    # Cria instância sem chamar __init__ completo
    watchdog = WatchdogAgent.__new__(WatchdogAgent)
    
    # Testa fallback (funciona apenas em Linux com /proc)
    cpu_percent = watchdog._get_cpu_fallback()
    assert isinstance(cpu_percent, float)
    assert 0.0 <= cpu_percent <= 100.0


@pytest.mark.unit
@pytest.mark.watchdog
def test_mem_fallback():
    """Testa fallback de leitura de RAM via /proc."""
    from agents.watchdog import WatchdogAgent
    
    watchdog = WatchdogAgent.__new__(WatchdogAgent)
    mem_percent = watchdog._get_mem_fallback()
    
    assert isinstance(mem_percent, float)
    assert 0.0 <= mem_percent <= 100.0


@pytest.mark.unit
@pytest.mark.watchdog
def test_disk_fallback():
    """Testa fallback de leitura de disco."""
    from agents.watchdog import WatchdogAgent
    
    watchdog = WatchdogAgent.__new__(WatchdogAgent)
    disk_percent = watchdog._get_disk_fallback()
    
    assert isinstance(disk_percent, float)
    assert 0.0 <= disk_percent <= 100.0


@pytest.mark.unit
@pytest.mark.watchdog
def test_proc_count_fallback():
    """Testa fallback de contagem de processos."""
    from agents.watchdog import WatchdogAgent
    
    watchdog = WatchdogAgent.__new__(WatchdogAgent)
    proc_count = watchdog._get_proc_count_fallback()
    
    assert isinstance(proc_count, int)
    assert proc_count > 0


# ─────────────────────────────────────────────────────────────
#  Testes de Execute Actions
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_execute_status(watchdog):
    """Testa ação 'status' do execute."""
    result = await watchdog._execute("status")
    
    assert result.success is True
    assert "cpu_percent" in result.data


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_execute_check_cost(watchdog):
    """Testa ação 'check_cost' do execute."""
    result = await watchdog._execute("check_cost", model="llama-3.3-70b")
    
    assert result.success is True
    assert result.data.get("authorized") is True


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_execute_health_check(watchdog):
    """Testa ação 'health_check' do execute."""
    # Mock para sistema saudável
    async def mock_health_check():
        return []  # Sem issues = saudável

    watchdog._perform_health_check = mock_health_check

    result = await watchdog._execute("health_check")

    assert result.success is True
    assert "issues" in result.data
    assert "healthy" in result.data


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_execute_alert_history(watchdog):
    """Testa ação 'alert_history' do execute."""
    # Gera alguns alertas
    watchdog._fire_alert("test1", "Alert 1")
    watchdog._fire_alert("test2", "Alert 2")
    
    result = await watchdog._execute("alert_history")
    
    assert result.success is True
    assert "alerts" in result.data
    assert len(result.data["alerts"]) > 0


@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_execute_unknown_action(watchdog):
    """Testa ação desconhecida."""
    result = await watchdog._execute("unknown_action")
    
    assert result.success is False
    assert "Unknown action" in result.error


# ─────────────────────────────────────────────────────────────
#  Testes de Monitor Loop
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.watchdog
@pytest.mark.asyncio
async def test_monitor_loop_stops_cleanly():
    """Testa que monitor loop para limpo com stop_event."""
    watchdog = WatchdogAgent()
    await watchdog.initialize()
    
    # Set stop event
    watchdog._stop_event.set()
    
    # Aguarda loop parar
    await asyncio.sleep(0.5)
    
    assert watchdog._monitoring_task.done() or watchdog._monitoring_task.cancelled()
    await watchdog.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
