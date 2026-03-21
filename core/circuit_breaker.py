"""
CircuitBreaker — prevents runaway loops and cascading failures.
States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery).
Reference: Martin Fowler Circuit Breaker pattern.
"""
import asyncio
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from core.agent_base import TaskResult


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject calls
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5       # failures before OPEN
    recovery_timeout: float = 60.0   # seconds before HALF_OPEN
    success_threshold: int = 2       # successes in HALF_OPEN before CLOSED
    timeout: float = 30.0            # per-call timeout


class CircuitBreaker:
    """
    Per-agent circuit breaker.
    Usage:
        cb = CircuitBreaker("my_agent")
        result = await cb.call(agent._execute, "task")
    """

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self.logger = logging.getLogger(f"CircuitBreaker.{name}")

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                self.logger.info(f"[{self.name}] OPEN → HALF_OPEN after {elapsed:.0f}s")
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    async def call(self, func, *args, **kwargs) -> TaskResult:
        """Execute func through circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            return TaskResult(
                success=False,
                error=f"Circuit breaker OPEN for '{self.name}' — "
                      f"retry in {self._time_until_recovery():.0f}s"
            )
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout
            )
            self._on_success()
            return result
        except asyncio.TimeoutError:
            self._on_failure()
            return TaskResult(
                success=False,
                error=f"Timeout ({self.config.timeout}s) for '{self.name}'"
            )
        except Exception as e:
            self._on_failure()
            return TaskResult(success=False, error=str(e))

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self.logger.info(f"[{self.name}] HALF_OPEN → CLOSED ✅")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self.logger.warning(f"[{self.name}] HALF_OPEN → OPEN (probe failed)")
        elif self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            self.logger.warning(
                f"[{self.name}] CLOSED → OPEN "
                f"(failures={self._failure_count})"
            )

    def _time_until_recovery(self) -> float:
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.config.recovery_timeout - elapsed)

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self.logger.info(f"[{self.name}] manually reset to CLOSED")

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "time_until_recovery": self._time_until_recovery(),
        }