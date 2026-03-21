"""
Observability decorators for The Moon agents.
Non-intrusive: agents opt-in by applying @observe or @observe_agent.
Wraps _execute() calls automatically without modifying agent code.
"""
import time
import asyncio
import logging
import functools
from core.agent_base import TaskResult

logger = logging.getLogger(__name__)


def observe(agent_id: str = None, task_type: str = "general"):
    """
    Decorator for individual async functions.
    Usage:
        @observe(agent_id="my_agent")
        async def my_function(...) -> TaskResult:
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            from core.observability.observer import MoonObserver
            observer = MoonObserver.get_instance()
            aid = agent_id or func.__qualname__.split(".")[0].lower()
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                if isinstance(result, TaskResult):
                    await observer.record(
                        agent_id=aid,
                        success=result.success,
                        execution_time=result.execution_time or elapsed,
                        error=result.error,
                        task_type=task_type
                    )
                return result
            except Exception as e:
                elapsed = time.time() - start
                await observer.record(
                    agent_id=aid,
                    success=False,
                    execution_time=elapsed,
                    error=str(e),
                    task_type=task_type
                )
                raise
        return wrapper
    return decorator


def observe_agent(cls):
    """
    Class decorator — wraps _execute() of any AgentBase subclass.
    Usage:
        @observe_agent
        class MyAgent(AgentBase):
            ...
    """
    original_execute = cls._execute

    @functools.wraps(original_execute)
    async def observed_execute(self, task: str, **kwargs) -> TaskResult:
        from core.observability.observer import MoonObserver
        observer = MoonObserver.get_instance()
        agent_id = getattr(self, 'AGENT_ID', cls.__name__.lower())
        task_type = kwargs.get("task_type", task.split()[0] if task else "general")
        start = time.time()
        try:
            result = await original_execute(self, task, **kwargs)
            elapsed = time.time() - start
            if isinstance(result, TaskResult):
                await observer.record(
                    agent_id=agent_id,
                    success=result.success,
                    execution_time=result.execution_time or elapsed,
                    error=result.error,
                    task_type=task_type[:30]
                )
            return result
        except Exception as e:
            elapsed = time.time() - start
            await observer.record(
                agent_id=agent_id,
                success=False,
                execution_time=elapsed,
                error=str(e)[:200],
                task_type=task_type[:30]
            )
            raise

    cls._execute = observed_execute
    return cls