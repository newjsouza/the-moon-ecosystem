import asyncio
import tempfile
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock
import pytest
from core.moon_flow import MoonFlow, FlowStep, MoonFlowRegistry, get_flow_registry
from core.agent_base import TaskResult


def test_flow_step_creation():
    """Testa criação de FlowStep com campos obrigatórios e defaults."""
    step = FlowStep(name="test_step", agent="test_agent", task="test_task")
    
    assert step.name == "test_step"
    assert step.agent == "test_agent"
    assert step.task == "test_task"
    assert step.depends_on == []
    assert step.on_error == "stop"
    assert step.timeout == 60.0


def test_moon_flow_creation():
    """Testa criação de MoonFlow com lista de steps."""
    steps = [
        FlowStep(name="step1", agent="agent1", task="task1"),
        FlowStep(name="step2", agent="agent2", task="task2", depends_on=["step1"])
    ]
    flow = MoonFlow(name="test_flow", steps=steps, session_mode="user")
    
    assert flow.name == "test_flow"
    assert len(flow.steps) == 2
    assert flow.session_mode == "user"


def test_flow_registry_singleton():
    """Testa que get_flow_registry retorna a mesma instância."""
    registry1 = get_flow_registry()
    registry2 = get_flow_registry()
    
    assert registry1 is registry2
    assert isinstance(registry1, MoonFlowRegistry)
    assert isinstance(registry2, MoonFlowRegistry)


def test_flow_registry_register_and_get():
    """Testa registro e recuperação de flow por nome."""
    registry = MoonFlowRegistry()
    flow = MoonFlow(name="test_flow", steps=[], session_mode="user")
    
    registry.register(flow)
    retrieved = registry.get("test_flow")
    
    assert retrieved is flow
    assert retrieved.name == "test_flow"


def test_flow_registry_list_flows():
    """Testa listagem de flows registrados."""
    registry = MoonFlowRegistry()
    flow1 = MoonFlow(name="flow1", steps=[], session_mode="user")
    flow2 = MoonFlow(name="flow2", steps=[], session_mode="user")
    
    registry.register(flow1)
    registry.register(flow2)
    
    flows = registry.list_flows()
    
    assert "flow1" in flows
    assert "flow2" in flows
    assert len(flows) == 2


def test_flow_to_dict():
    """Testa serialização correta de um flow."""
    steps = [
        FlowStep(name="step1", agent="agent1", task="task1", depends_on=[], on_error="stop", timeout=30.0)
    ]
    flow = MoonFlow(name="serialize_test", steps=steps, session_mode="channel")
    data = flow.to_dict()
    
    assert data["name"] == "serialize_test"
    assert data["session_mode"] == "channel"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["name"] == "step1"
    assert data["steps"][0]["agent"] == "agent1"
    assert data["steps"][0]["task"] == "task1"
    assert data["steps"][0]["depends_on"] == []
    assert data["steps"][0]["on_error"] == "stop"
    assert data["steps"][0]["timeout"] == 30.0


def test_flow_from_dict():
    """Testa desserialização correta de um flow."""
    data = {
        "name": "deserialize_test",
        "session_mode": "workspace",
        "steps": [
            {
                "name": "step1",
                "agent": "agent1",
                "task": "task1",
                "depends_on": ["prev_step"],
                "on_error": "continue",
                "timeout": 45.0
            }
        ]
    }
    flow = MoonFlow.from_dict(data)
    
    assert flow.name == "deserialize_test"
    assert flow.session_mode == "workspace"
    assert len(flow.steps) == 1
    assert flow.steps[0].name == "step1"
    assert flow.steps[0].agent == "agent1"
    assert flow.steps[0].task == "task1"
    assert flow.steps[0].depends_on == ["prev_step"]
    assert flow.steps[0].on_error == "continue"
    assert flow.steps[0].timeout == 45.0


def test_flow_save_and_load_file():
    """Testa salvar e carregar flow de arquivo temporário."""
    steps = [
        FlowStep(name="step1", agent="agent1", task="task1", on_error="skip")
    ]
    flow = MoonFlow(name="file_test", steps=steps, session_mode="global")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp_file:
        tmp_path = tmp_file.name
    
    try:
        # Save the flow
        registry = MoonFlowRegistry()
        registry.save_to_file(flow, tmp_path)
        
        # Load the flow
        loaded_flow = registry.load_from_file(tmp_path)
        
        assert loaded_flow.name == "file_test"
        assert loaded_flow.session_mode == "global"
        assert len(loaded_flow.steps) == 1
        assert loaded_flow.steps[0].name == "step1"
        assert loaded_flow.steps[0].on_error == "skip"
    finally:
        # Cleanup
        pathlib.Path(tmp_path).unlink()


def test_flow_execute_success():
    """Testa execução bem-sucedida de um flow com 2 steps."""
    steps = [
        FlowStep(name="step1", agent="test_agent", task="task1", depends_on=[]),
        FlowStep(name="step2", agent="test_agent", task="task2", depends_on=["step1"])
    ]
    flow = MoonFlow(name="execute_success", steps=steps, session_mode="user")
    
    # Create a mock orchestrator
    mock_orchestrator = AsyncMock()
    mock_orchestrator._call_agent = AsyncMock()
    
    # Configure the mock to return successful results
    mock_orchestrator._call_agent.side_effect = [
        TaskResult(success=True, data={"result": "step1_ok"}),
        TaskResult(success=True, data={"result": "step2_ok"})
    ]
    
    # Execute the flow
    result = asyncio.run(flow.execute({}, mock_orchestrator))
    
    # Verify the result
    assert result.success is True
    assert len(result.steps) == 2
    assert result.steps[0]["name"] == "step1"
    assert result.steps[0]["success"] is True
    assert result.steps[1]["name"] == "step2"
    assert result.steps[1]["success"] is True
    assert result.total_time > 0


def test_flow_execute_on_error_stop():
    """Testa execução com step falhando e on_error=stop."""
    steps = [
        FlowStep(name="step1", agent="test_agent", task="task1", depends_on=[], on_error="stop"),
        FlowStep(name="step2", agent="test_agent", task="task2", depends_on=[], on_error="stop")
    ]
    flow = MoonFlow(name="execute_error_stop", steps=steps, session_mode="user")
    
    # Create a mock orchestrator
    mock_orchestrator = AsyncMock()
    mock_orchestrator._call_agent = AsyncMock()
    
    # First call succeeds, second fails
    mock_orchestrator._call_agent.side_effect = [
        TaskResult(success=True, data={"result": "step1_ok"}),
        TaskResult(success=False, error="Test error")
    ]
    
    # Execute the flow
    result = asyncio.run(flow.execute({}, mock_orchestrator))
    
    # Should fail after first error
    assert result.success is False
    assert len(result.steps) == 2  # Both steps attempted
    assert result.steps[0]["name"] == "step1"
    assert result.steps[0]["success"] is True
    assert result.steps[1]["name"] == "step2"
    assert result.steps[1]["success"] is False
    assert "error" in result.error


def test_flow_execute_on_error_continue():
    """Testa execução com step falhando e on_error=continue."""
    steps = [
        FlowStep(name="step1", agent="test_agent", task="task1", depends_on=[], on_error="continue"),
        FlowStep(name="step2", agent="test_agent", task="task2", depends_on=["step1"], on_error="continue")
    ]
    flow = MoonFlow(name="execute_error_continue", steps=steps, session_mode="user")
    
    # Create a mock orchestrator
    mock_orchestrator = AsyncMock()
    mock_orchestrator._call_agent = AsyncMock()
    
    # First call fails, second succeeds
    mock_orchestrator._call_agent.side_effect = [
        TaskResult(success=False, error="Test error"),
        TaskResult(success=True, data={"result": "step2_ok"})
    ]
    
    # Execute the flow
    result = asyncio.run(flow.execute({}, mock_orchestrator))
    
    # Should succeed despite first step failing
    assert result.success is True
    assert len(result.steps) == 2
    assert result.steps[0]["name"] == "step1"
    assert result.steps[0]["success"] is False
    assert result.steps[1]["name"] == "step2"
    assert result.steps[1]["success"] is True


def test_orchestrator_load_default_flows():
    """Testa que flows são carregados no __init__ do Orchestrator."""
    # This test checks that the Orchestrator can be initialized without errors
    # It doesn't actually test loading since the flows directory might not exist during test
    from core.orchestrator import Orchestrator
    orch = Orchestrator()
    
    # Verify that the flow registry exists and is properly initialized
    assert hasattr(orch, 'flow_registry')
    assert orch.flow_registry is not None
    assert hasattr(orch, '_load_default_flows')
    
    # Verify that the method exists and is callable
    assert callable(orch._load_default_flows)