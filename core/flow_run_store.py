"""
core/flow_run_store.py
Persistent storage for MoonFlow executions with observability and audit trail.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading


@dataclass
class FlowStepRun:
    """Represents a single step execution within a flow run."""
    step_name: str
    agent: str
    status: str  # "pending", "running", "success", "failed"
    started_at: float
    finished_at: float = 0.0
    error: str = ""
    output_summary: str = ""
    attempt: int = 1              # (número da tentativa atual)
    max_attempts: int = 1         # (total de tentativas permitidas)


@dataclass
class FlowRunRecord:
    """Represents a complete flow execution run."""
    run_id: str
    flow_name: str
    session_id: str
    status: str  # "pending", "running", "success", "failed", "cancelled"
    started_at: float
    finished_at: float = 0.0
    steps: List[FlowStepRun] = None
    context: Dict[str, Any] = None

    def __post_init__(self):
        if self.steps is None:
            self.steps = []
        if self.context is None:
            self.context = {}


class FlowRunStore:
    """Persistent store for flow run records with JSON file backend."""

    def __init__(self, base_dir: str = "runtime/flows"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._runs_file = self.base_dir / "runs.jsonl"

    def save_run(self, record: FlowRunRecord) -> None:
        """Save a flow run record to persistent storage."""
        with self._lock:
            # Write as JSONL for easy appending
            with open(self._runs_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record)) + "\n")

    def load_run(self, run_id: str) -> Optional[FlowRunRecord]:
        """Load a specific flow run by run_id."""
        with self._lock:
            if not self._runs_file.exists():
                return None

            with open(self._runs_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if data["run_id"] == run_id:
                            return self._dict_to_record(data)
                    except json.JSONDecodeError:
                        continue
            return None

    def list_runs(self, flow_name: str = None, status: str = None) -> List[FlowRunRecord]:
        """List flow runs with optional filtering."""
        with self._lock:
            if not self._runs_file.exists():
                return []

            runs = []
            with open(self._runs_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if flow_name and data["flow_name"] != flow_name:
                            continue
                        if status and data["status"] != status:
                            continue
                        runs.append(self._dict_to_record(data))
                    except json.JSONDecodeError:
                        continue
            return runs

    def update_step(self, run_id: str, step_run: FlowStepRun) -> None:
        """Update a specific step within a run."""
        with self._lock:
            # Load all runs to memory temporarily to update one step
            temp_runs = []
            found_run = False
            
            if self._runs_file.exists():
                with open(self._runs_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            if data["run_id"] == run_id:
                                # Update the step in this run
                                found_run = True
                                step_found = False
                                
                                # Update existing step or add new one
                                for i, existing_step in enumerate(data["steps"]):
                                    if existing_step["step_name"] == step_run.step_name:
                                        data["steps"][i] = asdict(step_run)
                                        step_found = True
                                        break
                                    
                                if not step_found:
                                    data["steps"].append(asdict(step_run))
                                
                                # Update the run's status if needed
                                if step_run.status == "failed":
                                    data["status"] = "failed"
                                    
                            temp_runs.append(data)
                        except json.JSONDecodeError:
                            continue

            # If the run doesn't exist yet, create it
            if not found_run:
                # This shouldn't happen in normal operation, but handle gracefully
                new_run = FlowRunRecord(
                    run_id=run_id,
                    flow_name="",  # We don't know the flow name here
                    session_id="",
                    status="running",
                    started_at=time.time(),
                    steps=[step_run]
                )
                temp_runs.append(asdict(new_run))

            # Rewrite the file with updated data
            with open(self._runs_file, "w", encoding="utf-8") as f:
                for run_data in temp_runs:
                    f.write(json.dumps(run_data) + "\n")

    def mark_finished(self, run_id: str, status: str) -> None:
        """Mark a run as finished with the given status."""
        with self._lock:
            temp_runs = []
            found_run = False
            
            if self._runs_file.exists():
                with open(self._runs_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            if data["run_id"] == run_id:
                                found_run = True
                                data["status"] = status
                                data["finished_at"] = time.time()
                            temp_runs.append(data)
                        except json.JSONDecodeError:
                            continue

            # If the run doesn't exist yet, create it as finished
            if not found_run:
                new_run = FlowRunRecord(
                    run_id=run_id,
                    flow_name="",  # We don't know the flow name here
                    session_id="",
                    status=status,
                    started_at=time.time(),
                    finished_at=time.time()
                )
                temp_runs.append(asdict(new_run))

            # Rewrite the file with updated data
            with open(self._runs_file, "w", encoding="utf-8") as f:
                for run_data in temp_runs:
                    f.write(json.dumps(run_data) + "\n")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about stored runs."""
        with self._lock:
            if not self._runs_file.exists():
                return {"total_runs": 0, "by_status": {}, "by_flow": {}}

            total_runs = 0
            by_status = {}
            by_flow = {}

            with open(self._runs_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        total_runs += 1

                        # Count by status
                        status = data["status"]
                        by_status[status] = by_status.get(status, 0) + 1

                        # Count by flow
                        flow_name = data["flow_name"]
                        by_flow[flow_name] = by_flow.get(flow_name, 0) + 1
                    except json.JSONDecodeError:
                        continue

            return {
                "total_runs": total_runs,
                "by_status": by_status,
                "by_flow": by_flow
            }

    def _dict_to_record(self, data: Dict[str, Any]) -> FlowRunRecord:
        """Convert dictionary data back to FlowRunRecord with proper types."""
        # Convert step dicts back to FlowStepRun objects
        steps = []
        for step_data in data.get("steps", []):
            steps.append(FlowStepRun(**step_data))
        
        record = FlowRunRecord(**{k: v for k, v in data.items() if k != "steps"})
        record.steps = steps
        return record


# Singleton instance
_flow_run_store = None
_flow_lock = threading.Lock()


def get_flow_run_store(base_dir: str = "runtime/flows") -> FlowRunStore:
    """Get singleton instance of FlowRunStore."""
    global _flow_run_store

    with _flow_lock:
        if _flow_run_store is None:
            _flow_run_store = FlowRunStore(base_dir)

    return _flow_run_store