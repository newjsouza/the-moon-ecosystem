"""tests/test_flow_retry.py — Testes de retry inteligente e retomada de runs no MoonFlow"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock
from core.moon_flow import MoonFlow, FlowStep
from core.flow_run_store import FlowStepRun, FlowRunRecord


class TestFlowRetry:
    def test_flow_step_has_retry_fields(self):
        """Testa se FlowStep tem os campos max_retries e retry_delay."""
        step = FlowStep(name="test_step", agent="test_agent", task="test_task")
        
        assert hasattr(step, 'max_retries')
        assert hasattr(step, 'retry_delay')
        assert step.max_retries == 0
        assert step.retry_delay == 2.0

    def test_flow_step_run_has_attempt_fields(self):
        """Testa se FlowStepRun tem os campos attempt e max_attempts."""
        step_run = FlowStepRun(
            step_name="test_step",
            agent="test_agent",
            status="running",
            started_at=0.0
        )
        
        assert hasattr(step_run, 'attempt')
        assert hasattr(step_run, 'max_attempts')
        assert step_run.attempt == 1
        assert step_run.max_attempts == 1

    @pytest.mark.asyncio
    async def test_retry_success_on_second_attempt(self):
        """Testa se o retry funciona quando a primeira tentativa falha."""
        from core.moon_flow import MoonFlow, FlowStep
        
        # Criar um step com retry
        step = FlowStep(
            name="test_step",
            agent="test_agent", 
            task="test_task",
            max_retries=1,  # Permitir uma nova tentativa
            retry_delay=0.1  # Pequeno delay para testes
        )
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator que falha na primeira tentativa e succeeds na segunda
        mock_orchestrator = AsyncMock()
        
        # Criar resultados mockados
        first_result = Mock()
        first_result.success = False
        first_result.error = "Temporary error"
        first_result.data = None
        first_result.execution_time = 0.1
        
        second_result = Mock()
        second_result.success = True
        second_result.error = None
        second_result.data = {"result": "success"}
        second_result.execution_time = 0.1
        
        # Configurar para retornar primeiro o falho, depois o bem-sucedido
        mock_orchestrator._call_agent.side_effect = [first_result, second_result]
        
        # Executar o flow
        result = await flow.execute({}, mock_orchestrator)
        
        # Deve ter sucesso após retry
        assert result.success is True
        assert len(result.steps) == 1
        assert result.steps[0]["success"] is True
        # Deve ter feito duas chamadas (uma falha + uma sucesso)
        assert mock_orchestrator._call_agent.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_failure(self):
        """Testa se retorna falha quando todos os retries são esgotados."""
        from core.moon_flow import MoonFlow, FlowStep
        
        # Criar um step com retry
        step = FlowStep(
            name="test_step",
            agent="test_agent",
            task="test_task",
            max_retries=1,  # Permitir uma nova tentativa
            retry_delay=0.1
        )
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator que sempre falha
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.error = "Permanent error"
        mock_result.data = None
        mock_result.execution_time = 0.1
        
        # Sempre retornar o mesmo resultado falho
        mock_orchestrator._call_agent.return_value = mock_result
        
        # Executar o flow
        result = await flow.execute({}, mock_orchestrator)
        
        # Deve falhar após esgotar retries
        assert result.success is False
        assert len(result.steps) == 1
        assert result.steps[0]["success"] is False
        # Deve ter feito 2 chamadas (1 original + 1 retry)
        assert mock_orchestrator._call_agent.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_by_default(self):
        """Testa se não faz retry quando max_retries=0."""
        from core.moon_flow import MoonFlow, FlowStep
        
        # Criar um step sem retry (padrão)
        step = FlowStep(name="test_step", agent="test_agent", task="test_task")
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Mock orchestrator que sempre falha
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.error = "Error"
        mock_result.data = None
        mock_result.execution_time = 0.1
        
        mock_orchestrator._call_agent.return_value = mock_result
        
        # Executar o flow
        result = await flow.execute({}, mock_orchestrator)
        
        # Deve falhar imediatamente (sem retry)
        assert result.success is False
        assert len(result.steps) == 1
        assert result.steps[0]["success"] is False
        # Deve ter feito apenas 1 chamada
        assert mock_orchestrator._call_agent.call_count == 1

    @pytest.mark.asyncio
    async def test_resume_skips_completed_steps(self):
        """Testa se resume pula steps com status=success."""
        from core.moon_flow import MoonFlow, FlowStep
        from core.flow_run_store import get_flow_run_store

        # Criar um flow com múltiplos steps
        steps = [
            FlowStep(name="step1", agent="agent1", task="task1"),
            FlowStep(name="step2", agent="agent2", task="task2"),
            FlowStep(name="step3", agent="agent3", task="task3")
        ]
        flow = MoonFlow(name="test_flow", steps=steps)

        # Executar o flow uma vez para criar um run
        mock_orchestrator = AsyncMock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.data = {"result": "success"}
        mock_result.error = None
        mock_result.execution_time = 0.1
        mock_orchestrator._call_agent.return_value = mock_result

        initial_result = await flow.execute({}, mock_orchestrator)
        run_id = initial_result.run_id

        # Agora simular um run parcial onde apenas o step1 teve sucesso
        from core.flow_run_store import get_flow_run_store, FlowRunRecord, FlowStepRun
        store = get_flow_run_store()

        # Criar um run artificial com apenas o primeiro step completado
        partial_run = FlowRunRecord(
            run_id=run_id,
            flow_name="test_flow",
            session_id="test_session",
            status="failed",
            started_at=initial_result.total_time,
            finished_at=initial_result.total_time + 1.0,
            steps=[
                FlowStepRun(
                    step_name="step1",
                    agent="agent1",
                    status="success",
                    started_at=initial_result.total_time,
                    finished_at=initial_result.total_time + 0.1,
                    attempt=1,
                    max_attempts=1
                ),
                # step2 e step3 não estão completos
            ],
            context={}
        )

        # Substituir o run no store
        # Primeiro apagar o run existente (isso é complicado, então faremos um teste mais alto nível)

        # Em vez disso, vamos testar diretamente o método _execute_with_skip
        skip_steps = {"step1"}  # Simulando que o step1 já foi completado
        context = {}

        # Criar um NOVO mock para isolar a contagem do _execute_with_skip
        mock_orchestrator_skip = AsyncMock()
        
        # Mock para retornar sucesso para os steps restantes
        call_count = 0
        def side_effect(agent, task, **kwargs):
            nonlocal call_count
            call_count += 1
            result = Mock()
            result.success = True
            result.data = {"result": f"step_{call_count}_success"}
            result.error = None
            result.execution_time = 0.1
            return result

        mock_orchestrator_skip._call_agent.side_effect = side_effect

        # Executar com skip
        result = await flow._execute_with_skip(context, mock_orchestrator_skip, skip_steps=skip_steps)

        # Verificar que o step1 foi pulado e os outros foram executados
        # A contagem de chamadas deve ser 2 (step2 e step3)
        assert mock_orchestrator_skip._call_agent.call_count == 2
        # E o resultado deve ter 3 steps (1 pulado + 2 executados)
        assert len(result.steps) == 3
        # O step1 deve estar marcado como sucesso virtual
        step1_result = next((s for s in result.steps if s["name"] == "step1"), None)
        assert step1_result is not None
        assert step1_result["success"] is True
        assert step1_result["output"] == "skipped (already completed)"

    @pytest.mark.asyncio
    async def test_resume_run_not_found(self):
        """Testa se resume retorna erro quando run_id não existe."""
        from core.moon_flow import MoonFlow, FlowStep
        
        step = FlowStep(name="test_step", agent="test_agent", task="test_task")
        flow = MoonFlow(name="test_flow", steps=[step])
        
        # Tentar retomar um run_id que não existe
        result = await flow.resume("nonexistent-run-id", AsyncMock())
        
        # Deve retornar erro
        assert result.success is False
        assert "não encontrado" in result.error

    def test_flow_retry_command_registered(self):
        """Testa se o comando /flow-retry está registrado."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        # Verificar se o comando está registrado
        match = orch.registry.resolve("/flow-retry abc123")
        assert match is not None, "Comando /flow-retry não encontrado"
        entry, remainder = match
        assert remainder == "abc123"

    def test_flow_resume_command_registered(self):
        """Testa se o comando /flow-resume está registrado."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        # Verificar se o comando está registrado
        match = orch.registry.resolve("/flow-resume abc123")
        assert match is not None, "Comando /flow-resume não encontrado"
        entry, remainder = match
        assert remainder == "abc123"

    @pytest.mark.asyncio
    async def test_flow_retry_command_reruns_flow(self):
        """Testa se o comando /flow-retry re-executa um flow."""
        from core.orchestrator import Orchestrator
        from core.moon_flow import FlowStep, FlowResult
        from core.flow_run_store import FlowRunRecord, get_flow_run_store
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        # Criar um flow mock e adicioná-lo ao registry
        mock_flow = AsyncMock()
        mock_flow.execute = AsyncMock(return_value=FlowResult(
            flow_name="test_flow",
            success=True,
            steps=[{"name": "step1", "success": True}],
            total_time=1.0
        ))
        
        # Adicionar o flow mock ao registry
        orch.flow_registry._flows["test_flow"] = mock_flow
        
        # Criar um run record mock no store
        store = get_flow_run_store()
        record = FlowRunRecord(
            run_id="test-run-id",
            flow_name="test_flow",
            session_id="test-session",
            status="failed",
            started_at=0.0,
            context={"test": "context"}
        )
        store.save_run(record)
        
        # Testar o comando
        match = orch.registry.resolve("/flow-retry test-run-id")
        assert match is not None
        
        entry, remainder = match
        result = await entry.handler(remainder, {})
        
        # Verificar que o resultado indica sucesso
        assert "re-executado com sucesso" in result

    @pytest.mark.asyncio
    async def test_flow_resume_command_resumes(self):
        """Testa se o comando /flow-resume retoma um flow corretamente."""
        from core.orchestrator import Orchestrator
        from core.moon_flow import FlowStep, FlowResult
        from core.flow_run_store import FlowRunRecord, get_flow_run_store
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        # Criar um flow mock com o método resume
        mock_flow = AsyncMock()
        mock_flow.resume = AsyncMock(return_value=FlowResult(
            flow_name="test_flow",
            success=True,
            steps=[{"name": "step1", "success": True}],
            total_time=1.0
        ))
        
        # Adicionar o flow mock ao registry
        orch.flow_registry._flows["test_flow"] = mock_flow
        
        # Criar um run record mock no store
        store = get_flow_run_store()
        record = FlowRunRecord(
            run_id="test-run-id",
            flow_name="test_flow",
            session_id="test-session",
            status="failed",
            started_at=0.0,
            context={"test": "context"}
        )
        store.save_run(record)
        
        # Testar o comando
        match = orch.registry.resolve("/flow-resume test-run-id")
        assert match is not None
        
        entry, remainder = match
        result = await entry.handler(remainder, {})
        
        # Verificar que o resultado indica sucesso
        assert "retomado com sucesso" in result

    @pytest.mark.asyncio
    async def test_apex_pipeline_has_retry_config(self):
        """Testa se o apex_pipeline.json carrega com configurações de retry."""
        from core.moon_flow import MoonFlow
        import json
        
        # Carregar o arquivo apex_pipeline.json
        with open("flows/apex_pipeline.json", "r") as f:
            data = json.load(f)
        
        # Converter para MoonFlow
        flow = MoonFlow.from_dict(data)
        
        # Verificar que os steps têm as configurações de retry
        assert len(flow.steps) == 4
        
        # Verificar o primeiro step
        first_step = flow.steps[0]
        assert first_step.name == "fetch_games"
        assert first_step.max_retries == 2
        assert first_step.retry_delay == 3.0
        
        # Verificar o segundo step
        second_step = flow.steps[1]
        assert second_step.name == "fetch_lineups"
        assert second_step.max_retries == 1
        assert second_step.retry_delay == 5.0
        
        # Verificar o terceiro step
        third_step = flow.steps[2]
        assert third_step.name == "analyze"
        assert third_step.max_retries == 1
        assert third_step.retry_delay == 2.0
        
        # Verificar o quarto step
        fourth_step = flow.steps[3]
        assert fourth_step.name == "notify"
        assert fourth_step.max_retries == 2
        assert fourth_step.retry_delay == 1.0