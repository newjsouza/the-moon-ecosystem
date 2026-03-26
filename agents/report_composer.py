"""
agents/report_composer.py
Composes structured Telegram reports from RadarAgent scan output.
Uses LLMRouter for intelligent summarization with a structured fallback.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime

from core.agent_base import AgentBase, AgentPriority, TaskResult

logger = logging.getLogger("moon.agents.report_composer")

_CATEGORY_ICONS: dict[str, str] = {
    "llm_model":       "🤖",
    "code_repository": "🔥",
    "article":         "📰",
    "python_package":  "📦",
    "demo_app":        "🎮",
    "general":         "📌",
}

_REPORT_PROMPT = """You are The Moon's strategic intelligence analyst.
You received {total_new} new technology signals from a proactive radar scan.
Timestamp: {timestamp} | Scan type: {scan_type}

Raw data (JSON — max 30 items):
{data}

Write a concise Telegram report in PORTUGUESE (pt-BR):
- Use Telegram-compatible formatting: *bold*, _italic_, [text](url)
- Group items by category using the emoji icons: 🤖 LLM | 🔥 GitHub | 📰 Artigos | 📦 PyPI | 🎮 Demos
- Show at most 3 items per category (most impactful first)
- End with a section "💡 *Oportunidade para o Moon:*" — one concrete suggestion
  of something The Moon ecosystem could implement based on these findings
- Total length: under 3000 characters
- Do NOT use # markdown headers
- Start response with EXACTLY this header:
🌙 *The Moon — Radar Inteligente*
_{timestamp}_
"""


class ReportComposerAgent(AgentBase):
    """
    Composes Telegram reports from RadarAgent data via LLM + structured fallback.
    kwargs expected in _execute():
        radar_data (dict): TaskResult.data from RadarAgent
        scan_type  (str):  'quick_pulse' | 'full_scan' | 'strategic_digest'
    """

    def __init__(self, llm=None, message_bus=None) -> None:
        super().__init__()
        self.name = "ReportComposerAgent"
        self.description = "LLM-powered Telegram report composer from radar scan data."
        self.priority = AgentPriority.MEDIUM
        self._llm = llm
        self._message_bus = message_bus

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        start = time.time()
        radar_data: dict = kwargs.get("radar_data", {})
        scan_type: str = kwargs.get("scan_type", "full_scan")

        new_items: list[dict] = radar_data.get("new_items", [])
        total_new: int = radar_data.get("total_new", len(new_items))
        total_scanned: int = radar_data.get("total_scanned", 0)
        timestamp = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")

        if total_new == 0:
            report = (
                f"🌙 *The Moon — Radar Inteligente*\n_{timestamp}_\n\n"
                f"✅ Radar executado: {total_scanned} itens analisados.\n"
                f"💤 Sem novidades desde a última varredura."
            )
            return TaskResult(
                success=True,
                data={"report": report, "scan_type": scan_type, "total_new": 0},
                execution_time=time.time() - start,
            )

        report_text = ""
        if self._llm:
            prompt = _REPORT_PROMPT.format(
                total_new=total_new,
                timestamp=timestamp,
                scan_type=scan_type,
                data=json.dumps(new_items[:30], ensure_ascii=False, indent=2),
            )
            try:
                result = await self._llm.complete(prompt, task_type="general")
                if result and len(result.strip()) >= 80:
                    report_text = result.strip()
                else:
                    raise ValueError(f"LLM returned too short: {repr(result)}")
            except Exception as e:
                logger.warning(f"[ReportComposer] LLM failed, using fallback: {e}")

        if not report_text:
            report_text = self._fallback_report(new_items, timestamp, scan_type, total_scanned)

        return TaskResult(
            success=True,
            data={
                "report": report_text,
                "scan_type": scan_type,
                "total_new": total_new,
                "total_scanned": total_scanned,
                "char_count": len(report_text),
            },
            execution_time=time.time() - start,
        )

    def _fallback_report(
        self,
        items: list[dict],
        timestamp: str,
        scan_type: str,
        total_scanned: int,
    ) -> str:
        """Structured fallback when LLM is unavailable."""
        by_category: dict[str, list[dict]] = {}
        for item in items:
            by_category.setdefault(item.get("category", "general"), []).append(item)

        lines = [f"🌙 *The Moon — Radar Inteligente*", f"_{timestamp}_", ""]
        for cat, cat_items in by_category.items():
            icon = _CATEGORY_ICONS.get(cat, "📌")
            lines.append(f"{icon} *{cat.replace('_', ' ').title()}*")
            for item in cat_items[:3]:
                title = (item.get("title") or "")[:60]
                url = item.get("url", "")
                lines.append(f"• [{title}]({url})" if url else f"• {title}")
            lines.append("")
        lines.append(f"_Scan: {scan_type} | {len(items)} novos de {total_scanned} analisados_")
        return "\n".join(lines)
