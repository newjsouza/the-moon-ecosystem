"""
core/agent_base.py
Abstract base class for agents.
"""
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Dict, Optional
import time

class AgentPriority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class TaskResult:
    def __init__(self, success: bool, data: Any = None, error: Optional[str] = None, execution_time: float = 0.0):
        self.success = success
        self.data = data
        self.error = error
        self.execution_time = execution_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time": self.execution_time
        }

class AgentBase(ABC):
    def __init__(self):
        self.name = self.__class__.__name__
        self.description = "Base agent"
        self.priority = AgentPriority.MEDIUM
        self.is_initialized = False
        self.stats = {
            "execution_count": 0,
            "success_count": 0,
            "error_count": 0,
            "total_execution_time": 0.0
        }

    async def initialize(self) -> None:
        """Initialize resources"""
        self.is_initialized = True

    async def execute(self, task: str, **kwargs) -> TaskResult:
        """Wrapper for _execute with timing and metrics"""
        if not self.is_initialized:
            await self.initialize()

        self.stats["execution_count"] += 1
        start_time = time.time()
        
        try:
            result = await self._execute(task, **kwargs)
            execution_time = time.time() - start_time
            if result.success:
                self.stats["success_count"] += 1
            else:
                self.stats["error_count"] += 1
            result.execution_time = execution_time
            self.stats["total_execution_time"] += execution_time
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            self.stats["error_count"] += 1
            self.stats["total_execution_time"] += execution_time
            return TaskResult(success=False, error=str(e), execution_time=execution_time)

    @abstractmethod
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """Actual implementation to be overridden."""
        pass

    async def shutdown(self) -> None:
        """Cleanup resources"""
        self.is_initialized = False
