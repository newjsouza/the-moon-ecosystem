"""
agents/system_agent.py
System-level interaction agent for Linux.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from core.system.manager import SystemManager
from core.system.shortcuts import ShortcutListener
from utils.logger import setup_logger
import threading

class SystemAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.CRITICAL
        self.description = "Native Linux Integration Agent (Audio/Shortcuts)"
        self.logger = setup_logger("SystemAgent")
        self.manager = SystemManager()
        self.listener = ShortcutListener(system_manager=self.manager)
        self._listener_thread = None

    def _start_listener_background(self):
        """Run the shortcut listener in a background thread."""
        self.logger.info("Starting background shortcut listener...")
        self.listener.start()

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        self.logger.info(f"SystemAgent received task: {task}")
        
        if task == "start_listener":
            if not self._listener_thread or not self._listener_thread.is_alive():
                self._listener_thread = threading.Thread(target=self._start_listener_background, daemon=True)
                self._listener_thread.start()
                return TaskResult(success=True, data={"status": "listener_started"})
            return TaskResult(success=True, data={"status": "already_running"})

        elif task == "handle_intent":
            intent = kwargs.get("intent")
            params = kwargs.get("params", {})
            success = self.manager.handle_intent(intent, params)
            return TaskResult(success=success)

        return TaskResult(success=False, error=f"Unknown system task: {task}")
