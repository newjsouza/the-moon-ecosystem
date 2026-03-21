"""
LoopTask — unit of work in the AutonomousLoop task queue.
Serializable to JSON for persistence between sessions.
"""
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"   # skipped due to open circuit breaker


@dataclass
class LoopTask:
    """A single task in the autonomous loop queue."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_id: str = ""
    task: str = ""
    kwargs: dict = field(default_factory=dict)
    priority: int = 5           # 1 (highest) to 10 (lowest)
    max_retries: int = 3
    retry_count: int = 0
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_summary: Optional[str] = None
    error: Optional[str] = None
    use_evaluator: bool = True  # run through EvaluatorAgent after completion
    domain: str = "general"     # for EvaluatorAgent domain criteria

    @property
    def execution_time(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    @property
    def is_retryable(self) -> bool:
        return (self.status == TaskStatus.FAILED and
                self.retry_count < self.max_retries)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LoopTask":
        data = dict(data)
        data["status"] = TaskStatus(data.get("status", "pending"))
        return cls(**data)

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self, summary: str = "") -> None:
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.time()
        self.result_summary = summary[:200] if summary else ""

    def mark_failed(self, error: str = "") -> None:
        self.status = TaskStatus.FAILED
        self.completed_at = time.time()
        self.error = error[:200] if error else ""
        self.retry_count += 1

    def mark_skipped(self, reason: str = "") -> None:
        self.status = TaskStatus.SKIPPED
        self.completed_at = time.time()
        self.error = reason