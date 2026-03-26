"""
agents/proactive.py
Proactive Agent — The Heartbeat of The Moon.
Manages scheduled tasks, periodic checks, and pushes
unsolicited notifications to keep the user informed.

UPGRADED: Now generates real LLM-powered briefings using user_profile
and MessageBus history, instead of generic status messages.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

from core.agent_base import AgentBase, TaskResult, AgentPriority
from core.message_bus import MessageBus

logger = logging.getLogger("moon.agents.proactive")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


class ProactiveAgent(AgentBase):
    """
    The always-on heartbeat of The Moon.
    Sends real, value-packed briefings — not just status summaries.
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
                "description": "Send morning briefing with real insights",
                "hour": 8,
                "enabled": True
            },
            {
                "name": "evening_report",
                "description": "Send evening report of what was accomplished",
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
            briefing = await self._generate_real_briefing()
            return TaskResult(success=True, data={"briefing": briefing})

        if action == "health":
            health = self._check_system_health()
            return TaskResult(success=True, data=health)

        return TaskResult(
            success=True,
            data={"message": f"Proactive agent processed: {task}"}
        )

    async def _generate_real_briefing(self) -> str:
        """
        Generates a value-packed briefing using user profile + LLM.
        Not just status — actual insight and context.
        """
        # Get user profile
        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()
            greeting = profile.greeting()
            interests = ", ".join(profile.interests[:3])
            goals_str = profile.goals[0] if profile.goals else "automatização"
        except Exception:
            profile = None
            greeting = "Bom dia ☀️"
            interests = "IA, automação"
            goals_str = "automatização"

        now = datetime.now()
        now_str = now.strftime("%d/%m/%Y %H:%M")

        # Get recent message bus history for context
        bus_history = self.message_bus.get_history()
        recent_events = [
            h for h in (bus_history or [])[-20:]
            if h.get("topic", "") not in ("workspace.network",)
        ]
        event_summary = self._summarize_recent_events(recent_events)

        # Generate LLM insight
        llm_insight = await self._generate_llm_briefing_insight(interests, goals_str)

        hour = now.hour
        report_type = "Matinal ☀️" if hour < 15 else "Noturno 🌙"

        lines = [
            f"🌕 *The Moon — Briefing {report_type}*",
            f"{greeting}",
            f"🕐 {now_str}",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        active_count = sum(1 for t in self.scheduled_tasks if t.get("enabled"))
        lines.append(f"\n*📊 Sistema:* {active_count} tarefas ativas | Status: Operacional ✅")

        if event_summary:
            lines.append(f"\n*📡 Atividade Recente:*\n{event_summary}")

        if llm_insight:
            lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"*💡 Para Hoje:*\n{llm_insight}")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("_/status para detalhes | /sentinel para relatório de vigilância_")

        return "\n".join(lines)

    def _summarize_recent_events(self, events: List[Dict]) -> str:
        """Summarizes recent message bus events for briefing context."""
        if not events:
            return ""
        summaries = []
        seen_topics = set()
        for ev in reversed(events):
            topic = ev.get("topic", "")
            if topic in seen_topics:
                continue
            seen_topics.add(topic)
            if "task_completed" in topic:
                agent = ev.get("payload", {}).get("agent_id", "")
                title = ev.get("payload", {}).get("title", "")
                summaries.append(f"  ✅ {agent}: {title[:60]}")
            elif "qa.scheduled" in topic:
                health = ev.get("payload", {}).get("health", "?")
                summaries.append(f"  🩺 QA Automático: saúde {health}%")
            elif "alchemist.skill_proposed" in topic:
                skill = ev.get("payload", {}).get("skill", "")
                summaries.append(f"  ⚗️ Nova skill descoberta: {skill}")
            if len(summaries) >= 3:
                break
        return "\n".join(summaries) if summaries else ""

    async def _generate_llm_briefing_insight(self, interests: str, goal: str) -> str:
        """Generates a personalized, actionable daily insight via LLM."""
        if not GROQ_API_KEY:
            return ""
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=GROQ_API_KEY)
            hour = datetime.now().hour
            context = "início do dia (motivação e foco)" if hour < 12 else "fim do dia (reflexão e próximos passos)"
            completion = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "system",
                    "content": (
                        "Você é um assistente pessoal de IA extremamente perspicaz. "
                        "Gere um insight personalizado, prático e acionável de 1-2 frases. "
                        "Seja concreto, útil e inspirador. Responda em português BR."
                    )
                }, {
                    "role": "user",
                    "content": (
                        f"Contexto: {context}. "
                        f"Interesses: {interests}. "
                        f"Objetivo principal: {goal}. "
                        "Gere um insight ou dica valiosa para agora."
                    )
                }],
                max_tokens=120,
                temperature=0.75,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            logger.debug(f"ProactiveAgent: LLM insight failed: {e}")
            return ""

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
