"""
MoonObserverAgent — exposes health dashboard via MessageBus and Telegram.
Responds to 'health', 'metrics', 'dashboard' commands.
Persists session metrics on demand or on shutdown.
"""
import asyncio
import logging
from core.agent_base import AgentBase, TaskResult
from core.observability.observer import MoonObserver


class MoonObserverAgent(AgentBase):
    """
    Agent interface to MoonObserver metrics system.
    Handles: health report, agent metrics, slowest agents, dashboard.
    """

    AGENT_ID = "moon_observer"

    def __init__(self):
        super().__init__()
        self.observer = MoonObserver.get_instance()
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute observability commands.
        task options:
            'health'    → system health report
            'metrics'   → metrics for specific agent (agent_id=...)
            'slowest'   → top N slowest agents (top_n=5)
            'failing'   → top N most failing agents (top_n=5)
            'dashboard' → ASCII dashboard + health dict
            'persist'   → save session metrics to JSON
            'all'       → all metrics as dict
        """
        start = asyncio.get_event_loop().time()
        try:
            cmd = task.lower().strip()

            if cmd == "health":
                report = await self.observer.health_report()
                return TaskResult(
                    success=True,
                    data=report,
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "metrics":
                agent_id = kwargs.get("agent_id", "")
                if not agent_id:
                    return TaskResult(success=False,
                                      error="agent_id required for metrics command")
                metrics = self.observer.get_metrics(agent_id)
                if not metrics:
                    return TaskResult(success=False,
                                      error=f"No metrics found for agent: {agent_id}")
                return TaskResult(
                    success=True,
                    data=metrics.to_dict(),
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "slowest":
                top_n = kwargs.get("top_n", 5)
                slowest = await self.observer.get_slowest_agents(top_n)
                return TaskResult(
                    success=True,
                    data={"slowest_agents": slowest},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "failing":
                top_n = kwargs.get("top_n", 5)
                failing = await self.observer.get_most_failing_agents(top_n)
                return TaskResult(
                    success=True,
                    data={"most_failing_agents": failing},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "dashboard":
                self.observer.print_dashboard()
                report = await self.observer.health_report()
                return TaskResult(
                    success=True,
                    data=report,
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "persist":
                await self.observer.persist_session()
                return TaskResult(
                    success=True,
                    data={"persisted": True,
                          "session_id": self.observer._session_id},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "all":
                all_metrics = {
                    aid: m.to_dict()
                    for aid, m in self.observer.get_all_metrics().items()
                }
                return TaskResult(
                    success=True,
                    data={"agents": all_metrics,
                          "total_agents": len(all_metrics)},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown command: '{cmd}'. "
                          f"Valid: health, metrics, slowest, failing, dashboard, persist, all"
                )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )