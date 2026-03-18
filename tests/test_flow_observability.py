"""tests/test_flow_observability.py — Testes de observabilidade de flows"""

import pytest
import json
from unittest.mock import AsyncMock, Mock
import tempfile
import os
import time

@pytest.mark.asyncio
class TestFlowObservability:
    async def test_moon_flow_persists_run_id(self):
        """Testa se o MoonFlow persiste o run_id."""
        from core.moon_flow import MoonFlow, FlowStep
        from core.flow_run_store import get_flow_run_store
        
        # Create a simple flow with one step
        step = FlowStep(name="test_step", agent="test_agent", task="test task")
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.data = {"result": "test"}
        mock_result.error = None
        mock_result.execution_time = 0.1
        mock_orchestrator._call_agent.return_value = mock_result
        
        # Execute flow
        result = await flow.execute({}, mock_orchestrator)
        
        # Verify run_id is present
        assert result.run_id != ""
        
        # Verify run was persisted
        store = get_flow_run_store()
        persisted_run = store.load_run(result.run_id)
        assert persisted_run is not None
        assert persisted_run.flow_name == "test_flow"
        assert persisted_run.status == "success"

    async def test_moon_flow_records_step_success(self):
        """Testa se o MoonFlow registra sucesso de step."""
        from core.moon_flow import MoonFlow, FlowStep
        from core.flow_run_store import get_flow_run_store
        
        # Create a simple flow with one step
        step = FlowStep(name="test_step", agent="test_agent", task="test task")
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.data = {"result": "test"}
        mock_result.error = None
        mock_result.execution_time = 0.1
        mock_orchestrator._call_agent.return_value = mock_result
        
        # Execute flow
        result = await flow.execute({}, mock_orchestrator)
        
        # Verify run was persisted with successful step
        store = get_flow_run_store()
        persisted_run = store.load_run(result.run_id)
        assert persisted_run is not None
        assert len(persisted_run.steps) == 1
        assert persisted_run.steps[0].status == "success"
        assert persisted_run.steps[0].step_name == "test_step"

    async def test_moon_flow_records_step_failure(self):
        """Testa se o MoonFlow registra falha de step."""
        from core.moon_flow import MoonFlow, FlowStep
        from core.flow_run_store import get_flow_run_store
        
        # Create a simple flow with one step
        step = FlowStep(name="test_step", agent="test_agent", task="test task")
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator to simulate failure
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.data = None
        mock_result.error = "Test error"
        mock_result.execution_time = 0.1
        mock_orchestrator._call_agent.return_value = mock_result
        
        # Execute flow
        result = await flow.execute({}, mock_orchestrator)
        
        # Verify run was persisted with failed step
        store = get_flow_run_store()
        persisted_run = store.load_run(result.run_id)
        assert persisted_run is not None
        assert len(persisted_run.steps) == 1
        assert persisted_run.steps[0].status == "failed"
        assert persisted_run.steps[0].step_name == "test_step"
        assert persisted_run.steps[0].error == "Test error"
        assert persisted_run.status == "failed"

    async def test_flow_status_command_registered(self):
        """Testa se o comando /flow-status está registrado."""
        from core.orchestrator import Orchestrator
        
        # Create orchestrator instance
        orch = Orchestrator()
        orch._register_builtin_commands()  # Explicitly register commands
        
        # Check if command is registered
        match = orch.registry.resolve("/flow-status abc123")
        assert match is not None, "Comando /flow-status não encontrado no registry"
        entry, remainder = match
        assert remainder == "abc123"  # The part after the command

    async def test_flow_runs_command_registered(self):
        """Testa se o comando /flow-runs está registrado."""
        from core.orchestrator import Orchestrator
        
        # Create orchestrator instance
        orch = Orchestrator()
        orch._register_builtin_commands()  # Explicitly register commands
        
        # Check if command is registered
        match = orch.registry.resolve("/flow-runs test_flow")
        assert match is not None, "Comando /flow-runs não encontrado no registry"
        entry, remainder = match
        assert remainder == "test_flow"  # The part after the command

    async def test_flow_status_command_execution(self):
        """Testa a execução do comando /flow-status."""
        from core.moon_flow import MoonFlow, FlowStep
        from core.orchestrator import Orchestrator
        
        # Create a simple flow and execute it to generate a run_id
        step = FlowStep(name="test_step", agent="test_agent", task="test task")
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.data = {"result": "test"}
        mock_result.error = None
        mock_result.execution_time = 0.1
        mock_orchestrator._call_agent.return_value = mock_result
        
        # Execute flow
        result = await flow.execute({}, mock_orchestrator)
        run_id = result.run_id
        
        # Create orchestrator to test command
        orch = Orchestrator()
        orch._register_builtin_commands()  # Register the commands
        
        # Execute the command via the registry
        match = orch.registry.resolve(f"/flow-status {run_id}")
        assert match is not None, "Comando /flow-status não encontrado"
        
        entry, remainder = match
        # Call the handler function
        response = await entry.handler(remainder, {})
        
        # Response should contain run information
        assert "Status do Flow Run" in response
        assert run_id[:8] in response  # Shortened run ID in response

    async def test_flow_runs_command_execution(self):
        """Testa a execução do comando /flow-runs."""
        from core.moon_flow import MoonFlow, FlowStep
        from core.orchestrator import Orchestrator
        from core.flow_run_store import get_flow_run_store
        
        # Create and execute a flow to have some runs
        step = FlowStep(name="test_step", agent="test_agent", task="test task")
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.data = {"result": "test"}
        mock_result.error = None
        mock_result.execution_time = 0.1
        mock_orchestrator._call_agent.return_value = mock_result
        
        # Execute flow to create a run
        result = await flow.execute({}, mock_orchestrator)
        
        # Create orchestrator to test command
        orch = Orchestrator()
        orch._register_builtin_commands()  # Register the commands
        
        # Execute the command via the registry
        match = orch.registry.resolve("/flow-runs test_flow")
        assert match is not None, "Comando /flow-runs não encontrado"
        
        entry, remainder = match
        # Call the handler function
        response = await entry.handler(remainder, {})
        
        # Response should contain run information
        assert "Últimas execuções de" in response
        assert "test_flow" in response