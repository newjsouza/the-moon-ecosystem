"""
CodexUpdaterAgent — automatically appends sprint/feat entries
to MOON_CODEX.md whenever a task is completed.

Subscribes to:
  - architect.decision   → qualquer tarefa orquestrada
  - autonomous_loop.task_completed  → loop task finalizado
  - codex.update         → disparo manual ou por outro agente

Entry format injected into MOON_CODEX.md:
  ## [TYPE] <title> — [YYYY-MM-DD HH:MM]
  <generated summary>
"""
import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from core.agent_base import AgentBase, TaskResult
from core.observability.decorators import observe_agent
from agents.llm import LLMRouter
from core.message_bus import MessageBus

CODEX_PATH = Path("MOON_CODEX.md")


@observe_agent
class CodexUpdaterAgent(AgentBase):
    """
    Listens for completed tasks and appends structured entries
    to MOON_CODEX.md. Uses LLM to generate concise summaries.
    Falls back to rule-based summary if LLM unavailable.

    Commands (via _execute):
        'update'  — append entry from kwargs
        'verify'  — check CODEX integrity
        'status'  — list recent CODEX entries
    """

    AGENT_ID = "codex_updater"
    SUBSCRIBE_TOPICS = [
        "codex.update",
        "autonomous_loop.task_completed",
    ]

    def __init__(self):
        super().__init__()
        self.llm = LLMRouter()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._lock = asyncio.Lock()
        self.bus = MessageBus()

    async def start(self) -> None:
        """Subscribe to MessageBus topics."""
        await super().start()
        for topic in self.SUBSCRIBE_TOPICS:
            self.bus.subscribe(topic, self._on_event)
        self.logger.info(
            f"CodexUpdaterAgent started — "
            f"watching {self.SUBSCRIBE_TOPICS}"
        )

    async def _on_event(self, message) -> None:
        """Handle incoming MessageBus events."""
        try:
            payload = message.payload
            if isinstance(payload, dict):
                entry_type = payload.get("type", "feat")
                title = payload.get("title") or payload.get("task", "")
                details = payload.get("details") or payload.get("data", {})
                agent_id = payload.get("agent_id", message.sender)

                if not title:
                    return

                await self._append_entry(
                    entry_type=entry_type,
                    title=title,
                    agent_id=agent_id,
                    details=details,
                    topic=message.topic,
                )
        except Exception as e:
            self.logger.error(f"CodexUpdater _on_event error: {e}")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        start = asyncio.get_event_loop().time()
        cmd = task.lower().strip()

        try:
            if cmd == "update":
                await self._append_entry(
                    entry_type=kwargs.get("type", "feat"),
                    title=kwargs.get("title", "Manual Update"),
                    agent_id=kwargs.get("agent_id", "manual"),
                    details=kwargs.get("details", {}),
                    topic="codex.update",
                )
                return TaskResult(
                    success=True,
                    data={"appended": True},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "verify":
                result = self._verify_codex()
                return TaskResult(
                    success=True,
                    data=result,
                    execution_time=asyncio.get_event_loop().time() - start
                )

            elif cmd == "status":
                entries = self._list_recent_entries(n=10)
                return TaskResult(
                    success=True,
                    data={"recent_entries": entries},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            else:
                return TaskResult(
                    success=False,
                    error=f"Unknown command: {cmd}. Valid: update, verify, status"
                )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _append_entry(self, entry_type: str, title: str,
                             agent_id: str, details: dict,
                             topic: str) -> None:
        """
        Atomic append to MOON_CODEX.md.
        Uses tmp file + rename for atomicity.
        """
        async with self._lock:
            summary = await self._generate_summary(
                entry_type, title, agent_id, details
            )
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = self._format_entry(
                entry_type, title, agent_id, summary, timestamp
            )
            await self._atomic_append(entry)
            self.logger.info(
                f"MOON_CODEX.md updated: [{entry_type}] {title}"
            )

    async def _generate_summary(self, entry_type: str, title: str,
                                  agent_id: str, details: dict) -> str:
        """Generate concise summary via LLM or rule-based fallback."""
        # Rule-based fallback (always available)
        fallback = self._rule_based_summary(entry_type, agent_id, details)

        try:
            prompt = f"""Write a concise MOON_CODEX.md entry (3-5 bullet points, Portuguese, markdown).
Type: {entry_type}
Title: {title}
Agent: {agent_id}
Details: {str(details)[:500]}

Format:
- Key change or feature implemented
- Files created/modified
- Integration points
- Tests added (if any)

Max 100 words total. Be specific, no filler."""

            summary = await self.llm.complete(
                prompt, task_type="fast", actor="codex_updater_agent"
            )
            return summary.strip() if summary else fallback
        except Exception:
            return fallback

    def _rule_based_summary(self, entry_type: str,
                             agent_id: str, details: dict) -> str:
        """Deterministic summary when LLM unavailable."""
        files = details.get("files_created", [])
        tests = details.get("tests_added", 0)
        lines = [f"- Agente: `{agent_id}`"]
        if files:
            for f in files[:4]:
                lines.append(f"- Criado: `{f}`")
        if tests:
            lines.append(f"- Testes adicionados: {tests}")
        steps = details.get("steps_completed", [])
        if steps:
            lines.append(f"- Steps: {', '.join(steps)}")
        return "\n".join(lines) if lines else f"- Implementação {entry_type} concluída"

    def _format_entry(self, entry_type: str, title: str,
                       agent_id: str, summary: str,
                       timestamp: str) -> str:
        """Format CODEX entry block."""
        icon = {
            "feat": "🆕", "fix": "🔧", "docs": "📄",
            "sprint": "🚀", "refactor": "♻️", "test": "🧪",
        }.get(entry_type, "📌")

        return (
            f"\n### {icon} [{entry_type.upper()}] {title} — [{timestamp}]\n\n"
            f"**Agent:** `{agent_id}`\n\n"
            f"{summary}\n\n"
            f"---\n"
        )

    async def _atomic_append(self, entry: str) -> None:
        """Write to tmp file then rename — prevents partial writes."""
        codex = CODEX_PATH.resolve()
        current = codex.read_text(encoding="utf-8") if codex.exists() else ""

        # Write new content to temp file in same directory
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=codex.parent, suffix=".codex.tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(current + entry)
            shutil.move(tmp_path, str(codex))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _verify_codex(self) -> dict:
        """Check CODEX integrity — size, encoding, last entry."""
        if not CODEX_PATH.exists():
            return {"exists": False, "error": "MOON_CODEX.md not found"}
        content = CODEX_PATH.read_text(encoding="utf-8")
        lines = content.splitlines()
        headers = [l for l in lines if l.startswith("##")]
        return {
            "exists": True,
            "size_kb": round(CODEX_PATH.stat().st_size / 1024, 1),
            "lines": len(lines),
            "h2_sections": len(headers),
            "last_entry": headers[-1] if headers else None,
        }

    def _list_recent_entries(self, n: int = 10) -> list:
        """Return last N ## headers from CODEX."""
        if not CODEX_PATH.exists():
            return []
        lines = CODEX_PATH.read_text(encoding="utf-8").splitlines()
        headers = [l for l in lines if l.startswith("##")]
        return headers[-n:]
