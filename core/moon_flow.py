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

    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []


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

    async def execute(self, context: Dict[str, Any], orchestrator) -> FlowResult:
        import uuid
        from core.flow_run_store import get_flow_run_store
        
        # Generate unique run ID
        run_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Get session ID from context if available
        session_id = context.get("session_id", "unknown")
        
        # Create and save initial run record
        from core.flow_run_store import FlowRunRecord, FlowStepRun
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
                    # Record step start
                    step_started_at = time.time()
                    step_run = FlowStepRun(
                        step_name=step.name,
                        agent=step.agent,
                        status="running",
                        started_at=step_started_at
                    )
                    store.update_step(run_id, step_run)

                    # Execute the agent task
                    result = await asyncio.wait_for(
                        orchestrator._call_agent(step.agent, task_with_context, timeout=step.timeout),
                        timeout=step.timeout
                    )

                    step_result = {
                        "name": step.name,
                        "success": result.success,
                        "output": result.data,
                        "error": result.error,
                        "execution_time": result.execution_time
                    }
                    
                    results.append(step_result)
                    
                    # Update step status
                    step_run.finished_at = time.time()
                    step_run.status = "success" if result.success else "failed"
                    step_run.output_summary = str(result.data)[:200] if result.data else ""
                    step_run.error = result.error or ""
                    store.update_step(run_id, step_run)
                    
                    # Store output for potential use by subsequent steps
                    step_outputs[f"step_{step.name}"] = result.data
                    
                    if result.success:
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
                except asyncio.TimeoutError:
                    step_result = {
                        "name": step.name,
                        "success": False,
                        "output": None,
                        "error": f"Step '{step.name}' timed out after {step.timeout}s",
                        "execution_time": step.timeout
                    }
                    results.append(step_result)
                    
                    # Update step status for timeout
                    step_run.finished_at = time.time()
                    step_run.status = "failed"
                    step_run.error = step_result["error"]
                    store.update_step(run_id, step_run)
                    
                    if step.on_error == "stop":
                        store.mark_finished(run_id, "failed")
                        return FlowResult(
                            flow_name=self.name,
                            success=False,
                            steps=results,
                            total_time=time.time() - start_time,
                            error=f"Step '{step.name}' timed out and on_error='stop'",
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
                    
                    # Update step status for exception
                    step_run.finished_at = time.time()
                    step_run.status = "failed"
                    step_run.error = str(e)
                    store.update_step(run_id, step_run)
                    
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