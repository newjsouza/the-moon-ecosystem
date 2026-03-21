"""
AgentMetrics — per-agent performance data structure.
Tracks: calls, successes, failures, avg execution time, error types.
Serializable to JSON for persistence.
"""
import time
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from typing import Optional


@dataclass
class AgentMetrics:
    """Metrics snapshot for a single agent."""
    agent_id: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_execution_time: float = 0.0
    min_execution_time: float = float('inf')
    max_execution_time: float = 0.0
    last_call_timestamp: float = 0.0
    last_error: Optional[str] = None
    error_counts: dict = field(default_factory=dict)
    task_type_counts: dict = field(default_factory=dict)

    @property
    def avg_execution_time(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_execution_time / self.total_calls

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    def record(self, success: bool, execution_time: float,
               error: str = None, task_type: str = "general") -> None:
        """Record a single agent call."""
        self.total_calls += 1
        self.total_execution_time += execution_time
        self.last_call_timestamp = time.time()

        if execution_time < self.min_execution_time:
            self.min_execution_time = execution_time
        if execution_time > self.max_execution_time:
            self.max_execution_time = execution_time

        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            if error:
                self.last_error = error[:200]
                self.error_counts[error[:50]] = \
                    self.error_counts.get(error[:50], 0) + 1

        self.task_type_counts[task_type] = \
            self.task_type_counts.get(task_type, 0) + 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["avg_execution_time"] = self.avg_execution_time
        d["success_rate"] = self.success_rate
        if self.min_execution_time == float('inf'):
            d["min_execution_time"] = 0.0
        return d

    def to_summary(self) -> str:
        """Human-readable one-line summary."""
        rate = f"{self.success_rate:.0%}"
        avg = f"{self.avg_execution_time:.2f}s"
        return (f"[{self.agent_id}] calls={self.total_calls} "
                f"success={rate} avg={avg} "
                f"errors={self.failed_calls}")