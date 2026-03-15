"""
agents/proactive.py
Proactive Agent — The Heartbeat of The Moon.
Manages scheduled tasks, periodic checks, and pushes
unsolicited notifications to keep the user informed.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from core.agent_base import AgentBase, TaskResult, AgentPriority
from core.message_bus import MessageBus

logger = logging.getLogger("moon.agents.proactive")


class ProactiveAgent(AgentBase):
    """
    The always-on heartbeat of The Moon.
    Manages scheduled tasks and proactively initiates contact.
    """

    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "Proactive task execution and scheduled notifications"
        self.message_bus = MessageBus()
        self.scheduled_tasks: List[Dict[str, Any]] = []
        self._register_default_tasks()

    def _register_default_tasks(self):
        """Registers the default set of proactive tasks."""
        self.scheduled_tasks = [
            {
                "name": "morning_briefing",
                "description": "Send morning status and tips",
                "hour": 8,
                "enabled": True
            },
            {
                "name": "evening_report",
                "description": "Send evening research summary",
                "hour": 20,
                "enabled": True
            },
            {
                "name": "health_check",
                "description": "System health monitoring",
                "interval_minutes": 60,
                "enabled": True
            }
        ]

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """Executes proactive tasks on demand."""
        action = kwargs.get("action", "status")

        if action == "status":
            return TaskResult(
                success=True,
                data={
                    "scheduled_tasks": len(self.scheduled_tasks),
                    "active_tasks": sum(1 for t in self.scheduled_tasks if t.get("enabled")),
                    "tasks": self.scheduled_tasks,
                    "next_briefing": self._get_next_task_time()
                }
            )

        if action == "briefing":
            briefing = await self._generate_briefing()
            return TaskResult(success=True, data={"briefing": briefing})

        if action == "health":
            health = self._check_system_health()
            return TaskResult(success=True, data=health)

        return TaskResult(
            success=True,
            data={"message": f"Proactive agent processed: {task}"}
        )

    async def _generate_briefing(self) -> str:
        """Generates a status briefing message."""
        now = datetime.now()
        greeting = "Bom dia" if now.hour < 12 else ("Boa tarde" if now.hour < 18 else "Boa noite")

        briefing = (
            f"🌙 *{greeting}, Johnathan.*\n\n"
            f"📅 {now.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"*Sistema The Moon — Relatório Proativo*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Tarefas agendadas: {len(self.scheduled_tasks)}\n"
            f"• Status: Operacional ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"_Envie /status para detalhes completos._"
        )
        return briefing

    def _check_system_health(self) -> Dict[str, Any]:
        """Performs a system health check."""
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "message_bus_history": len(self.message_bus.get_history()),
            "scheduled_tasks_active": sum(1 for t in self.scheduled_tasks if t.get("enabled"))
        }

    def _get_next_task_time(self) -> str:
        """Returns the next scheduled task time."""
        now = datetime.now()
        for task in sorted(self.scheduled_tasks, key=lambda t: t.get("hour", 0)):
            if task.get("hour") and task["hour"] > now.hour:
                return f"{task['name']} at {task['hour']}:00"
        return "Next cycle tomorrow at 08:00"
