"""
agents/moon_sentinel.py
MoonSentinelAgent — O Núcleo de Vontade do The Moon.

O agente mais proativo do ecossistema. Não espera ser chamado.
Age como um sócio vigilante: observa, detecta, propõe e notifica
ANTES que o usuário precise pedir.

RESPONSABILIDADES:
  1. Vigilância de tendências tecnológicas (a cada 4h)
  2. Monitoramento de saúde do ecossistema (a cada 1h)
  3. Proposta e notificação de novas skills (via SkillAlchemist)
  4. Geração de relatórios de iniciativa (08:00 e 20:00)

ASSINATURA IMUTÁVEL (Moon Codex):
  async def _execute(self, task: str, **kwargs) -> TaskResult
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus

logger = logging.getLogger("moon.agents.sentinel")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# How often each watch cycle runs
TECH_WATCH_INTERVAL_HOURS = 4
HEALTH_WATCH_INTERVAL_MINUTES = 60
INITIATIVES_LOG = Path("data/sentinel_initiatives.json")


class MoonSentinelAgent(AgentBase):
    """
    The proactive vigilance brain of The Moon.

    Runs autonomous watch cycles and pushes insights to the user
    without waiting to be asked.
    """

    def __init__(self, orchestrator=None) -> None:
        super().__init__()
        self.name = "MoonSentinelAgent"
        self.priority = AgentPriority.HIGH
        self.description = "Proactive vigilance, trend watching, ecosystem health, initiative reports"
        self.orchestrator = orchestrator
        self.message_bus = MessageBus()

        # State
        self._last_tech_watch: float = 0.0
        self._last_health_watch: float = 0.0
        self._watch_task: Optional[asyncio.Task] = None
        self._initiatives: List[Dict[str, Any]] = []

        # Subscribe to events from other agents
        self.message_bus.subscribe("alchemist.skill_proposed", self._on_skill_proposed)
        self.message_bus.subscribe("devops.scan_complete", self._on_devops_scan)

        INITIATIVES_LOG.parent.mkdir(parents=True, exist_ok=True)
        self._load_initiatives()

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        self._watch_task = asyncio.create_task(
            self._sentinel_loop(), name="moon.sentinel.loop"
        )
        logger.info("MoonSentinelAgent initialized — sentinel loop started 🔭")

    async def shutdown(self) -> None:
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        self._save_initiatives()
        await super().shutdown()

    # ═══════════════════════════════════════════════════════════
    #  _execute — on-demand interface (Moon Codex contract)
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """Handles on-demand commands from the Orchestrator/Telegram."""
        action = task.strip().lower() if task else "status"

        if action in ("status", ""):
            return TaskResult(success=True, data=self._get_status())

        if action == "tech-watch":
            result = await self._watch_tech_trends()
            return TaskResult(success=True, data={"report": result})

        if action == "health":
            report = await self._watch_ecosystem_health()
            return TaskResult(success=True, data={"health": report})

        if action == "report" or action == "briefing":
            report = await self._generate_initiative_report(send_telegram=True)
            return TaskResult(success=True, data={"report": report})

        if action == "initiatives":
            return TaskResult(success=True, data={"initiatives": self._initiatives[-20:]})

        return TaskResult(
            success=True,
            data={"message": f"Sentinel recebeu: '{task}'. Use: status|tech-watch|health|report|initiatives"}
        )

    # ═══════════════════════════════════════════════════════════
    #  Sentinel Loop — runs forever in background
    # ═══════════════════════════════════════════════════════════

    async def _sentinel_loop(self) -> None:
        """
        Main autonomous loop.
        Every minute checks if it's time for each watch cycle.
        """
        logger.info("Sentinel loop started — watching the horizon 🌐")
        await asyncio.sleep(15)  # Give system time to boot before first cycle

        while True:
            try:
                now = time.time()

                # Tech trend watch every 4 hours
                if now - self._last_tech_watch >= TECH_WATCH_INTERVAL_HOURS * 3600:
                    await self._watch_tech_trends()
                    self._last_tech_watch = time.time()

                # Ecosystem health watch every 60 minutes
                if now - self._last_health_watch >= HEALTH_WATCH_INTERVAL_MINUTES * 60:
                    await self._watch_ecosystem_health()
                    self._last_health_watch = time.time()

                # Scheduled reports (08:00 and 20:00)
                await self._maybe_scheduled_report()

            except asyncio.CancelledError:
                logger.info("Sentinel loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Sentinel loop error: {e}")

            await asyncio.sleep(60)  # Check every minute

    async def _maybe_scheduled_report(self) -> None:
        """Fires the initiative report at configured hours (default 08:00 and 20:00)."""
        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()
            hour = datetime.now().hour
            minute = datetime.now().minute

            trigger_hours = {
                profile.preferred_briefing_hour,
                profile.preferred_evening_report_hour,
            }

            if hour in trigger_hours and 0 <= minute < 2:
                # Only fire in the first 2 minutes of the trigger hour
                key = f"report_{datetime.now().strftime('%Y%m%d_%H')}"
                if not self._was_initiative_done_today(key):
                    await self._generate_initiative_report(send_telegram=True)
                    self._log_initiative(key, "scheduled_report", {})

        except Exception as e:
            logger.debug(f"_maybe_scheduled_report error: {e}")

    # ═══════════════════════════════════════════════════════════
    #  1. Tech Trend Watch
    # ═══════════════════════════════════════════════════════════

    async def _watch_tech_trends(self) -> str:
        """
        Fetches and synthesizes tech trends from ResearcherAgent + NewsMonitorAgent.
        Sends top insights to Telegram if notify_on_trend is enabled.
        """
        logger.info("Sentinel: starting tech trend watch cycle 🔭")

        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()
        except Exception:
            profile = None

        # The user specifically requested tracking these topics:
        base_topics = ["VibeCoding e IA Generativa", "Novidades AI (Anthropic, GPT, Gemini, Groq, Alibaba, DeepSeek)"]
        
        user_topics = (profile.watchlist_topics if profile else [])
        topics = base_topics + [t for t in user_topics if t not in base_topics][:2]

        findings = []

        # Use ResearcherAgent if available
        if self.orchestrator and "ResearcherAgent" in self.orchestrator._agents:
            for topic in topics[:3]:  # Limit to 3 topics per cycle
                try:
                    res = await asyncio.wait_for(
                        self.orchestrator._agents["ResearcherAgent"].execute(
                            topic, action="research"
                        ),
                        timeout=45.0,
                    )
                    if res.success and res.data:
                        summary = str(res.data)[:300]
                        findings.append(f"**{topic}**: {summary}")
                        logger.info(f"Sentinel: researched '{topic}'")
                except asyncio.TimeoutError:
                    logger.warning(f"Sentinel: research timeout for '{topic}'")
                except Exception as e:
                    logger.warning(f"Sentinel: research error for '{topic}': {e}")
                await asyncio.sleep(5)
        else:
            # Fallback: try to use LLM directly
            findings = await self._llm_trend_synthesis(topics[:4])

        if not findings:
            logger.info("Sentinel: no trend findings this cycle")
            return "Nenhuma tendência detectada neste ciclo."

        report = self._format_trend_report(findings)
        
        # Save the actual text of the findings and the report so the Dashboard can display it
        self._log_initiative("tech_watch", "tech_trend", {
            "topics": topics[:3], 
            "findings": findings,
            "report": report
        })

        # Only notify if profile allows
        if profile is None or (profile.notify_on_trend and profile.should_notify_now()):
            await self._send_telegram(report)

        return report

    async def _llm_trend_synthesis(self, topics: List[str]) -> List[str]:
        """Fallback: synthesize trends via LLM when ResearcherAgent is unavailable."""
        if not GROQ_API_KEY:
            return []
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=GROQ_API_KEY)
            topics_str = ", ".join(topics)
            completion = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "system",
                    "content": (
                        "Você é um analista de tendências tecnológicas especializado em IA e automação. "
                        "Forneça insights concisos e práticos sobre as tendências solicitadas. "
                        "Responda em português BR, em formato de bullet points curtos."
                    )
                }, {
                    "role": "user",
                    "content": (
                        f"Quais são as principais tendências e novidades recentes em: {topics_str}?\n"
                        "Foco em novidades práticas, ferramentas open-source, e oportunidades. "
                        "Máximo 4 pontos, cada um com no máximo 150 caracteres."
                    )
                }],
                max_tokens=600,
                temperature=0.4,
            )
            raw = completion.choices[0].message.content.strip()
            lines = [l.strip().lstrip("•-*").strip() for l in raw.split("\n") if l.strip()]
            return lines[:4]
        except Exception as e:
            logger.warning(f"Sentinel: LLM trend synthesis failed: {e}")
            return []

    def _format_trend_report(self, findings: List[str]) -> str:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        lines = [f"🔭 *Sentinel — Tendências Detectadas*", f"🕐 {now}", ""]
        for i, f in enumerate(findings, 1):
            lines.append(f"{i}. {f[:280]}")
        lines.append("\n_Próxima varredura em 4 horas._")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    #  2. Ecosystem Health Watch
    # ═══════════════════════════════════════════════════════════

    async def _watch_ecosystem_health(self) -> Dict[str, Any]:
        """
        Monitors agents health. If circuit breakers are open or agents are
        failing, proposes auto-correction and notifies the user.
        """
        logger.info("Sentinel: checking ecosystem health 🩺")
        issues = []
        healthy = []

        if self.orchestrator:
            for name, circuit in self.orchestrator._circuits.items():
                if circuit.open:
                    issues.append(f"⚠️ Agente `{name}` — circuit ABERTO (falhas consecutivas)")
                else:
                    healthy.append(name)

        if issues:
            self._log_initiative("health_issue", "ecosystem_health", {"issues": issues})
            try:
                from core.user_profile import get_user_profile
                profile = get_user_profile()
                if profile.notify_on_health_issue and profile.should_notify_now():
                    msg = (
                        "🩺 *Sentinel — Alerta de Saúde*\n\n"
                        + "\n".join(issues)
                        + "\n\n_Tentando auto-correção via AutonomousDevOpsRefactor..._"
                    )
                    await self._send_telegram(msg)
            except Exception:
                pass

            # Attempt auto-correction
            if self.orchestrator and "AutonomousDevOpsRefactor" in self.orchestrator._agents:
                try:
                    await asyncio.wait_for(
                        self.orchestrator._agents["AutonomousDevOpsRefactor"].execute(
                            "auto_fix", issues=issues
                        ),
                        timeout=30.0,
                    )
                except Exception as e:
                    logger.warning(f"Sentinel: auto-correction attempt failed: {e}")

        return {
            "healthy_agents": len(healthy),
            "issues": issues,
            "checked_at": datetime.now().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════
    #  3. New Skill Proposal (triggered by MessageBus event)
    # ═══════════════════════════════════════════════════════════

    async def _on_skill_proposed(self, payload: Dict[str, Any]) -> None:
        """
        Called when SkillAlchemist proposes a new skill.
        Evaluates it and, if approved, notifies the user for confirmation
        before integration (respects approve_before_skill_integration).
        """
        skill_name = payload.get("skill", "unknown")
        skill_path = payload.get("path", "")
        logger.info(f"Sentinel: new skill proposed — {skill_name}")

        self._log_initiative(
            f"skill_proposed_{skill_name}",
            "skill_discovery",
            {"skill": skill_name, "path": skill_path}
        )

        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()

            if not (profile.notify_on_new_skill and profile.should_notify_now()):
                return

            if profile.approve_before_skill_integration:
                msg = (
                    f"⚗️ *Sentinel — Nova Skill Descoberta!*\n\n"
                    f"📦 **{skill_name}**\n"
                    f"📁 `{skill_path}`\n\n"
                    f"O SkillAlchemist descobriu e avaliou esta ferramenta.\n"
                    f"Ela passou no sandbox e na verificação de compliance.\n\n"
                    f"✅ Responda *aprovar {skill_name}* para integrar ao ecossistema\n"
                    f"❌ Responda *rejeitar {skill_name}* para descartar"
                )
            else:
                msg = (
                    f"⚗️ *Sentinel — Nova Skill Integrada!*\n\n"
                    f"📦 **{skill_name}** foi integrada automaticamente ao ecossistema.\n"
                    f"📁 `{skill_path}`"
                )

            await self._send_telegram(msg)

        except Exception as e:
            logger.error(f"Sentinel: _on_skill_proposed error: {e}")

    async def _on_devops_scan(self, payload: Dict[str, Any]) -> None:
        """Called when AutonomousDevOpsRefactor completes a scan."""
        issues_found = payload.get("issues_found", 0)
        if issues_found > 0:
            self._log_initiative("devops_issues", "devops_scan", payload)
            logger.info(f"Sentinel: DevOps scan found {issues_found} issues")

    # ═══════════════════════════════════════════════════════════
    #  4. Initiative Report (Morning & Evening)
    # ═══════════════════════════════════════════════════════════

    async def _generate_initiative_report(self, send_telegram: bool = True) -> str:
        """
        Generates a rich report of what The Moon did proactively.
        Not just 'N tasks scheduled' — actual value delivered.
        """
        logger.info("Sentinel: generating initiative report 📋")

        try:
            from core.user_profile import get_user_profile
            profile = get_user_profile()
            greeting = profile.greeting()
            name = profile.name
        except Exception:
            greeting = "Olá"
            name = "Johnathan"

        # Collect recent initiatives (last 24h)
        now = time.time()
        recent = [
            i for i in self._initiatives
            if now - i.get("timestamp", 0) < 86400
        ]

        # Build report sections
        sections = []

        # What we discovered
        discoveries = [i for i in recent if i.get("type") == "skill_discovery"]
        if discoveries:
            items = "\n".join(f"  ⚗️ {d['key']}" for d in discoveries[:3])
            sections.append(f"*🔬 Descobertas:*\n{items}")

        # Trends watched
        watches = [i for i in recent if i.get("type") == "tech_trend"]
        if watches:
            sections.append(f"*🔭 Tendências monitoradas:* {len(watches)} ciclos de vigilância")

        # Health checks
        health_issues = [i for i in recent if i.get("type") == "ecosystem_health"]
        if health_issues:
            issue_count = sum(len(i.get("data", {}).get("issues", [])) for i in health_issues)
            sections.append(f"*🩺 Saúde:* {len(health_issues)} verificações, {issue_count} alertas")

        # Reports generated
        reports = [i for i in recent if i.get("type") == "scheduled_report"]

        # Enrich with actual LLM insight if available
        llm_insight = await self._generate_llm_insight(profile if profile else None)

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        hour = datetime.now().hour
        report_type = "☀️ Matinal" if hour < 15 else "🌙 Noturno"

        lines = [
            f"🌕 *The Moon — Relatório {report_type}*",
            f"{greeting}",
            f"🕐 {now_str}",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if sections:
            lines.append("\n*O que fiz hoje por você:*")
            lines.extend(sections)
        else:
            lines.append("\n*Sistema operando normalmente.*\n_Vigilância contínua ativa._")

        if llm_insight:
            lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"*💡 Insight do Momento:*\n{llm_insight}")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("_Use /sentinel para mais detalhes._")

        report = "\n".join(lines)

        if send_telegram:
            await self._send_telegram(report)

        return report

    async def _generate_llm_insight(self, profile) -> str:
        """Generates a personalized insight/tip via LLM."""
        if not GROQ_API_KEY:
            return ""
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=GROQ_API_KEY)
            interests = ", ".join((profile.interests if profile else []) or ["IA, automação"])
            completion = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "system",
                    "content": (
                        "Você é um assistente de IA proativo. Gere um insight ou dica prática "
                        "e acionável de 1-2 frases para um desenvolvedor focado nos tópicos dados. "
                        "Seja direto, útil e específico. Responda em português BR."
                    )
                }, {
                    "role": "user",
                    "content": f"Interesses: {interests}. Dê um insight valioso e prático para hoje."
                }],
                max_tokens=150,
                temperature=0.7,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            logger.debug(f"Sentinel: LLM insight failed: {e}")
            return ""

    # ═══════════════════════════════════════════════════════════
    #  Telegram Notifier
    # ═══════════════════════════════════════════════════════════

    async def _send_telegram(self, text: str) -> bool:
        """Sends a message to Telegram."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.debug("Sentinel: Telegram not configured, skipping notification")
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": text[:4096],
                        "parse_mode": "Markdown",
                    },
                )
                if resp.status_code == 200:
                    logger.info("Sentinel: Telegram notification sent ✉️")
                    return True
                else:
                    logger.warning(f"Sentinel: Telegram error {resp.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Sentinel: Telegram send failed: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    #  Initiative Log
    # ═══════════════════════════════════════════════════════════

    def _log_initiative(self, key: str, initiative_type: str, data: Dict[str, Any]) -> None:
        """Records a completed initiative."""
        entry = {
            "key": key,
            "type": initiative_type,
            "data": data,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }
        self._initiatives.append(entry)
        # Keep last 200 entries
        if len(self._initiatives) > 200:
            self._initiatives = self._initiatives[-200:]
        self._save_initiatives()

    def _was_initiative_done_today(self, key: str) -> bool:
        """Checks if an initiative with this key was already logged today."""
        today = datetime.now().strftime("%Y-%m-%d")  # Matches ISO format in stored datetime
        return any(
            i.get("key") == key and today in i.get("datetime", "")
            for i in self._initiatives
        )

    def _load_initiatives(self) -> None:
        try:
            if INITIATIVES_LOG.exists():
                with open(INITIATIVES_LOG, encoding="utf-8") as f:
                    self._initiatives = json.load(f)
        except Exception:
            self._initiatives = []

    def _save_initiatives(self) -> None:
        try:
            with open(INITIATIVES_LOG, "w", encoding="utf-8") as f:
                json.dump(self._initiatives, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Sentinel: failed to save initiatives: {e}")

    # ═══════════════════════════════════════════════════════════
    #  Status
    # ═══════════════════════════════════════════════════════════

    def _get_status(self) -> Dict[str, Any]:
        now = time.time()
        recent_24h = [i for i in self._initiatives if now - i.get("timestamp", 0) < 86400]
        return {
            "agent": "MoonSentinelAgent",
            "status": "active",
            "last_tech_watch": datetime.fromtimestamp(self._last_tech_watch).isoformat()
                if self._last_tech_watch > 0 else "never",
            "last_health_watch": datetime.fromtimestamp(self._last_health_watch).isoformat()
                if self._last_health_watch > 0 else "never",
            "initiatives_last_24h": len(recent_24h),
            "total_initiatives": len(self._initiatives),
            "next_tech_watch_in_minutes": max(
                0,
                int((self._last_tech_watch + TECH_WATCH_INTERVAL_HOURS * 3600 - now) / 60)
            ) if self._last_tech_watch > 0 else 0,
        }
