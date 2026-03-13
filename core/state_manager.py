"""
core/state_manager.py
Manages state and context for the system.
"""
from typing import Any, Dict
import time

class ContextEntry:
    def __init__(self, key: str, value: Any, ttl: int = None):
        self.key = key
        self.value = value
        self.timestamp = time.time()
        self.ttl = ttl
        
    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl

class StateManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StateManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self.context: Dict[str, ContextEntry] = {}
        self.memory: Dict[str, Any] = {}
        self._initialized = True

    def set_context(self, key: str, value: Any, ttl: int = None):
        self.context[key] = ContextEntry(key, value, ttl)

    def get_context(self, key: str, default: Any = None) -> Any:
        self._cleanup_expired()
        entry = self.context.get(key)
        if entry:
            return entry.value
        return default

    def _cleanup_expired(self):
        expired = [k for k, v in self.context.items() if v.is_expired()]
        for k in expired:
            del self.context[k]

    def set_memory(self, key: str, value: Any):
        self.memory[key] = value

    def get_memory(self, key: str, default: Any = None) -> Any:
        return self.memory.get(key, default)
