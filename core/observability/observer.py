"""
MoonObserver — central observability singleton.
Collects metrics from all agents, persists to JSON, provides health reports.
Thread-safe via asyncio. Zero external dependencies.
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional
from core.observability.metrics import AgentMetrics

logger = logging.getLogger(__name__)

METRICS_DIR = Path("data/metrics")
_instance: Optional["MoonObserver"] = None


class MoonObserver:
    """
    Singleton observer for The Moon ecosystem.
    Usage: observer = MoonObserver.get_instance()
    """

    def __new__(cls):
        global _instance
        if _instance is None:
            _instance = super().__new__(cls)
            _instance._initialized = False
        return _instance

    def __init__(self):
        if self._initialized:
            return
        self._metrics: dict[str, AgentMetrics] = {}
        self._session_start = time.time()
        self._session_id = f"session_{int(self._session_start)}"
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        (METRICS_DIR / "agents").mkdir(exist_ok=True)
        (METRICS_DIR / "sessions").mkdir(exist_ok=True)
        (METRICS_DIR / "errors").mkdir(exist_ok=True)
        self._initialized = True
        self.logger.info(f"MoonObserver initialized — session: {self._session_id}")

    @classmethod
    def get_instance(cls) -> "MoonObserver":
        return cls()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton — for testing only."""
        global _instance
        _instance = None

    def _get_metrics(self, agent_id: str) -> AgentMetrics:
        if agent_id not in self._metrics:
            self._metrics[agent_id] = AgentMetrics(agent_id=agent_id)
        return self._metrics[agent_id]

    async def record(self, agent_id: str, success: bool,
                     execution_time: float, error: str = None,
                     task_type: str = "general") -> None:
        """Record a single agent execution result."""
        async with self._lock:
            metrics = self._get_metrics(agent_id)
            metrics.record(success, execution_time, error, task_type)

    def record_sync(self, agent_id: str, success: bool,
                    execution_time: float, error: str = None,
                    task_type: str = "general") -> None:
        """Synchronous version for use in non-async contexts."""
        metrics = self._get_metrics(agent_id)
        metrics.record(success, execution_time, error, task_type)

    def get_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        return self._metrics.get(agent_id)

    def get_all_metrics(self) -> dict[str, AgentMetrics]:
        return dict(self._metrics)

    async def health_report(self) -> dict:
        """Generate system-wide health snapshot."""
        async with self._lock:
            agents_health = {}
            total_calls = 0
            total_errors = 0

            for agent_id, metrics in self._metrics.items():
                total_calls += metrics.total_calls
                total_errors += metrics.failed_calls
                agents_health[agent_id] = {
                    "calls": metrics.total_calls,
                    "success_rate": round(metrics.success_rate, 3),
                    "avg_time_s": round(metrics.avg_execution_time, 3),
                    "last_error": metrics.last_error,
                    "status": "healthy" if metrics.success_rate >= 0.8
                              else "degraded" if metrics.success_rate >= 0.5
                              else "unhealthy",
                }

            session_uptime = time.time() - self._session_start
            overall_rate = (
                (total_calls - total_errors) / total_calls
                if total_calls > 0 else 1.0
            )

            return {
                "session_id": self._session_id,
                "uptime_seconds": round(session_uptime, 1),
                "total_calls": total_calls,
                "total_errors": total_errors,
                "overall_success_rate": round(overall_rate, 3),
                "agents": agents_health,
                "system_status": (
                    "healthy" if overall_rate >= 0.9
                    else "degraded" if overall_rate >= 0.7
                    else "critical"
                ),
                "timestamp": time.time(),
            }

    async def persist_session(self) -> None:
        """Save session metrics to JSON file."""
        try:
            report = await self.health_report()
            session_file = METRICS_DIR / "sessions" / f"{self._session_id}.json"
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            self.logger.info(f"Session metrics saved: {session_file}")

            for agent_id, metrics in self._metrics.items():
                agent_file = METRICS_DIR / "agents" / f"{agent_id}.json"
                with open(agent_file, "w", encoding="utf-8") as f:
                    json.dump(metrics.to_dict(), f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to persist metrics: {e}")

    async def load_agent_history(self, agent_id: str) -> Optional[dict]:
        """Load persisted metrics for an agent."""
        agent_file = METRICS_DIR / "agents" / f"{agent_id}.json"
        try:
            if agent_file.exists():
                with open(agent_file) as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not load history for {agent_id}: {e}")
        return None

    async def get_slowest_agents(self, top_n: int = 5) -> list[dict]:
        """Return top N slowest agents by average execution time."""
        agents = [
            {"agent_id": aid, "avg_time": m.avg_execution_time,
             "calls": m.total_calls}
            for aid, m in self._metrics.items()
            if m.total_calls > 0
        ]
        return sorted(agents, key=lambda x: x["avg_time"], reverse=True)[:top_n]

    async def get_most_failing_agents(self, top_n: int = 5) -> list[dict]:
        """Return top N agents with highest failure rates."""
        agents = [
            {"agent_id": aid, "failure_rate": 1 - m.success_rate,
             "failed_calls": m.failed_calls}
            for aid, m in self._metrics.items()
            if m.total_calls > 0
        ]
        return sorted(agents, key=lambda x: x["failure_rate"], reverse=True)[:top_n]

    def print_dashboard(self) -> None:
        """Print ASCII health dashboard to stdout."""
        print("\n╔══════════════════════════════════════════════╗")
        print("║         THE MOON — HEALTH DASHBOARD          ║")
        print("╠══════════════════════════════════════════════╣")
        if not self._metrics:
            print("║  No metrics recorded yet                    ║")
        for agent_id, metrics in self._metrics.items():
            bar_len = int(metrics.success_rate * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"║ {agent_id[:18]:<18} [{bar}] "
                  f"{metrics.success_rate:.0%} ║")
        print("╚══════════════════════════════════════════════╝\n")