from __future__ import annotations
import asyncio
import time
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.agent_base import TaskResult


@dataclass
class FlowStep:
    name: str
    agent: str
    task: str
    depends_on: List[str] = None
    on_error: str = "stop"
    timeout: float = 60.0
    max_retries: int = 0          # (0 = sem retry)
    retry_delay: float = 2.0      # (segundos entre tentativas)
    retry_on: List[str] = None    # (None = retry em qualquer erro)

    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []
        if self.retry_on is None:
            self.retry_on = []


@dataclass
class FlowResult:
    flow_name: str
    success: bool
    steps: List[Dict[str, Any]]
    total_time: float
    error: str = None
    run_id: str = ""      # Added for observability
    session_id: str = ""  # Added for observability


class MoonFlow:
    def __init__(self, name: str, steps: List[FlowStep], session_mode: str = "user"):
        self.name = name
        self.steps = steps
        self.session_mode = session_mode

    async def _execute_step_with_retry(self, step, task_with_context, orchestrator, run_id, store, step_outputs):
        """
        Tenta executar um step até max_retries+1 vezes.
        Retorna (success, result_data, error_message)
        """
        import asyncio
        from core.flow_run_store import FlowStepRun
        attempts = step.max_retries + 1
        last_error = ""
        
        for attempt in range(1, attempts + 1):
            # Record step start with attempt info
            step_started_at = time.time()
            step_run = FlowStepRun(
                step_name=step.name,
                agent=step.agent,
                status="running",
                started_at=step_started_at,
                attempt=attempt,
                max_attempts=attempts
            )
            store.update_step(run_id, step_run)

            try:
                # Execute the agent task
                result = await asyncio.wait_for(
                    orchestrator._call_agent(step.agent, task_with_context, timeout=step.timeout),
                    timeout=step.timeout
                )

                if result.success:
                    # Update step status with success
                    step_run.finished_at = time.time()
                    step_run.status = "success"
                    step_run.output_summary = str(result.data)[:200] if result.data else ""
                    step_run.error = ""
                    store.update_step(run_id, step_run)
                    return True, result.data, ""
                
                last_error = result.error or "falha sem mensagem"
                
            except asyncio.TimeoutError:
                last_error = f"Step '{step.name}' timed out after {step.timeout}s"
                
                # Update step status for timeout
                step_run.finished_at = time.time()
                step_run.status = "failed"
                step_run.error = last_error
                step_run.output_summary = ""
                store.update_step(run_id, step_run)
            except Exception as e:
                last_error = str(e)
                
                # Update step status for exception
                step_run.finished_at = time.time()
                step_run.status = "failed"
                step_run.error = last_error
                step_run.output_summary = ""
                store.update_step(run_id, step_run)
            
            # If we have more attempts, wait before retrying
            if attempt < attempts:
                await asyncio.sleep(step.retry_delay)
        
        # All attempts failed
        return False, None, last_error

    async def resume(self, run_id: str, orchestrator) -> FlowResult:
        """
        Retoma execução de um run_id interrompido.
        Pula steps com status='success' e re-executa a partir do primeiro 'failed'.
        """
        from core.flow_run_store import get_flow_run_store
        store = get_flow_run_store()
        record = store.load_run(run_id)
        if not record:
            return FlowResult(
                flow_name=self.name, success=False,
                steps=[], total_time=0.0,
                error=f"run_id '{run_id}' não encontrado"
            )
        # Find steps that have succeeded
        completed_steps = {
            s.step_name for s in (record.steps or [])
            if s.status == "success"
        }
        # Use the original context from the record
        context = record.context or {}
        # Execute flow skipping completed steps
        return await self._execute_with_skip(context, orchestrator, skip_steps=completed_steps, resume_run_id=run_id)

    async def _execute_with_skip(self, context: Dict[str, Any], orchestrator, 
                                 skip_steps: set = None, 
                                 resume_run_id: str = None) -> FlowResult:
        import uuid
        from core.flow_run_store import get_flow_run_store, FlowStepRun
        
        # Use the provided run_id if resuming, otherwise generate a new one
        run_id = resume_run_id if resume_run_id else str(uuid.uuid4())
        start_time = time.time()
        
        # Get session ID from context if available
        session_id = context.get("session_id", "unknown")
        
        # Create and save initial run record if not resuming
        if not resume_run_id:
            from core.flow_run_store import FlowRunRecord, FlowStepRun
            store = get_flow_run_store()
            run_record = FlowRunRecord(
                run_id=run_id,
                flow_name=self.name,
                session_id=session_id,
                status="running",
                started_at=start_time,
                context=context
            )
            store.save_run(run_record)
        else:
            # If resuming, we'll reuse the existing run record
            from core.flow_run_store import get_flow_run_store
            store = get_flow_run_store()
        
        results = []
        step_outputs = {}

        # Execute steps respecting dependencies and on_error handling
        remaining_steps = self.steps[:]
        executed_steps = set()

        while remaining_steps:
            executed_in_this_round = 0
            for i, step in enumerate(remaining_steps[:]):
                # Check if all dependencies are satisfied
                ready = True
                for dep in step.depends_on:
                    if dep not in executed_steps:
                        ready = False
                        break

                if not ready:
                    continue

                # If this step was already completed successfully, skip it
                if skip_steps and step.name in skip_steps:
                    # Add a virtual success result for the skipped step
                    step_result = {
                        "name": step.name,
                        "success": True,
                        "output": "skipped (already completed)",
                        "error": "",
                        "execution_time": 0.0
                    }
                    results.append(step_result)
                    
                    # Try to get the original output from the store if available
                    from core.flow_run_store import get_flow_run_store
                    store = get_flow_run_store()
                    record = store.load_run(run_id)
                    if record and record.steps:
                        for stored_step in record.steps:
                            if stored_step.step_name == step.name and stored_step.output_summary:
                                step_outputs[f"step_{step.name}"] = stored_step.output_summary
                                break
                    
                    executed_steps.add(step.name)
                    remaining_steps.remove(step)
                    executed_in_this_round += 1
                    continue

                # Prepare the task string by replacing placeholders with actual values
                task_with_context = step.task.format(**context, **step_outputs)

                try:
                    # Execute step with retry logic
                    success, result_data, error_msg = await self._execute_step_with_retry(
                        step, task_with_context, orchestrator, run_id, store, step_outputs
                    )
                    
                    step_result = {
                        "name": step.name,
                        "success": success,
                        "output": result_data,
                        "error": error_msg,
                        "execution_time": time.time() - start_time
                    }
                    
                    results.append(step_result)
                    
                    # Store output for potential use by subsequent steps
                    step_outputs[f"step_{step.name}"] = result_data
                    
                    if success:
                        executed_steps.add(step.name)
                        remaining_steps.remove(step)
                        executed_in_this_round += 1
                    else:
                        if step.on_error == "stop":
                            store.mark_finished(run_id, "failed")
                            return FlowResult(
                                flow_name=self.name,
                                success=False,
                                steps=results,
                                total_time=time.time() - start_time,
                                error=f"Step '{step.name}' failed and on_error='stop'",
                                run_id=run_id,
                                session_id=session_id
                            )
                        elif step.on_error == "continue":
                            executed_steps.add(step.name)
                            remaining_steps.remove(step)
                            executed_in_this_round += 1
                        elif step.on_error == "skip":
                            executed_steps.add(step.name)
                            remaining_steps.remove(step)
                            executed_in_this_round += 1
                except Exception as e:
                    step_result = {
                        "name": step.name,
                        "success": False,
                        "output": None,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    }
                    results.append(step_result)
                    
                    if step.on_error == "stop":
                        store.mark_finished(run_id, "failed")
                        return FlowResult(
                            flow_name=self.name,
                            success=False,
                            steps=results,
                            total_time=time.time() - start_time,
                            error=f"Step '{step.name}' raised exception and on_error='stop': {str(e)}",
                            run_id=run_id,
                            session_id=session_id
                        )
                    elif step.on_error == "continue":
                        executed_steps.add(step.name)
                        remaining_steps.remove(step)
                        executed_in_this_round += 1
                    elif step.on_error == "skip":
                        executed_steps.add(step.name)
                        remaining_steps.remove(step)
                        executed_in_this_round += 1

            # If no steps were executed in this round, there's a circular dependency
            if executed_in_this_round == 0:
                store.mark_finished(run_id, "failed")
                return FlowResult(
                    flow_name=self.name,
                    success=False,
                    steps=results,
                    total_time=time.time() - start_time,
                    error="Circular dependency detected or unsatisfied dependencies",
                    run_id=run_id,
                    session_id=session_id
                )

        # All steps executed successfully
        if not resume_run_id:  # Only mark finished if we created a new run
            store.mark_finished(run_id, "success")
        return FlowResult(
            flow_name=self.name,
            success=True,
            steps=results,
            total_time=time.time() - start_time,
            run_id=run_id,
            session_id=session_id
        )

    async def execute(self, context: Dict[str, Any], orchestrator) -> FlowResult:
        import uuid
        from core.flow_run_store import get_flow_run_store, FlowStepRun
        
        # Generate unique run ID
        run_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Get session ID from context if available
        session_id = context.get("session_id", "unknown")
        
        # Create and save initial run record
        from core.flow_run_store import FlowRunRecord
        store = get_flow_run_store()
        run_record = FlowRunRecord(
            run_id=run_id,
            flow_name=self.name,
            session_id=session_id,
            status="running",
            started_at=start_time
        )
        store.save_run(run_record)
        
        results = []
        step_outputs = {}

        # Execute steps respecting dependencies and on_error handling
        remaining_steps = self.steps[:]
        executed_steps = set()

        while remaining_steps:
            executed_in_this_round = 0
            for i, step in enumerate(remaining_steps[:]):
                # Check if all dependencies are satisfied
                ready = True
                for dep in step.depends_on:
                    if dep not in executed_steps:
                        ready = False
                        break

                if not ready:
                    continue

                # Prepare the task string by replacing placeholders with actual values
                task_with_context = step.task.format(**context, **step_outputs)

                try:
                    # Execute step with retry logic
                    success, result_data, error_msg = await self._execute_step_with_retry(
                        step, task_with_context, orchestrator, run_id, store, step_outputs
                    )
                    
                    step_result = {
                        "name": step.name,
                        "success": success,
                        "output": result_data,
                        "error": error_msg,
                        "execution_time": time.time() - start_time  # This would need to be more precise in a real scenario
                    }
                    
                    results.append(step_result)
                    
                    # Store output for potential use by subsequent steps
                    step_outputs[f"step_{step.name}"] = result_data
                    
                    if success:
                        executed_steps.add(step.name)
                        remaining_steps.remove(step)
                        executed_in_this_round += 1
                    else:
                        if step.on_error == "stop":
                            store.mark_finished(run_id, "failed")
                            return FlowResult(
                                flow_name=self.name,
                                success=False,
                                steps=results,
                                total_time=time.time() - start_time,
                                error=f"Step '{step.name}' failed and on_error='stop'",
                                run_id=run_id,
                                session_id=session_id
                            )
                        elif step.on_error == "continue":
                            executed_steps.add(step.name)
                            remaining_steps.remove(step)
                            executed_in_this_round += 1
                        elif step.on_error == "skip":
                            executed_steps.add(step.name)
                            remaining_steps.remove(step)
                            executed_in_this_round += 1
                except Exception as e:
                    step_result = {
                        "name": step.name,
                        "success": False,
                        "output": None,
                        "error": str(e),
                        "execution_time": time.time() - start_time
                    }
                    results.append(step_result)
                    
                    if step.on_error == "stop":
                        store.mark_finished(run_id, "failed")
                        return FlowResult(
                            flow_name=self.name,
                            success=False,
                            steps=results,
                            total_time=time.time() - start_time,
                            error=f"Step '{step.name}' raised exception and on_error='stop': {str(e)}",
                            run_id=run_id,
                            session_id=session_id
                        )
                    elif step.on_error == "continue":
                        executed_steps.add(step.name)
                        remaining_steps.remove(step)
                        executed_in_this_round += 1
                    elif step.on_error == "skip":
                        executed_steps.add(step.name)
                        remaining_steps.remove(step)
                        executed_in_this_round += 1

            # If no steps were executed in this round, there's a circular dependency
            if executed_in_this_round == 0:
                store.mark_finished(run_id, "failed")
                return FlowResult(
                    flow_name=self.name,
                    success=False,
                    steps=results,
                    total_time=time.time() - start_time,
                    error="Circular dependency detected or unsatisfied dependencies",
                    run_id=run_id,
                    session_id=session_id
                )

        # All steps executed successfully
        store.mark_finished(run_id, "success")
        return FlowResult(
            flow_name=self.name,
            success=True,
            steps=results,
            total_time=time.time() - start_time,
            run_id=run_id,
            session_id=session_id
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "session_mode": self.session_mode,
            "steps": [asdict(step) for step in self.steps]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MoonFlow:
        steps = [FlowStep(**step_data) for step_data in data["steps"]]
        return cls(
            name=data["name"],
            steps=steps,
            session_mode=data.get("session_mode", "user")
        )


# Singleton instance for the flow registry
_flow_registry = None
_flow_lock = __import__('threading').Lock()


class MoonFlowRegistry:
    def __init__(self):
        self._flows: Dict[str, MoonFlow] = {}

    def register(self, flow: MoonFlow) -> None:
        self._flows[flow.name] = flow

    def get(self, name: str) -> Optional[MoonFlow]:
        return self._flows.get(name)

    def list_flows(self) -> List[str]:
        return list(self._flows.keys())

    def load_from_file(self, path: str) -> MoonFlow:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return MoonFlow.from_dict(data)

    def save_to_file(self, flow: MoonFlow, path: str) -> None:
        data = flow.to_dict()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def get_flow_registry() -> MoonFlowRegistry:
    global _flow_registry
    
    with _flow_lock:
        if _flow_registry is None:
            _flow_registry = MoonFlowRegistry()
    
    return _flow_registry