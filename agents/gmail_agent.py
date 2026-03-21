"""
GmailAgent — Intelligent email management via Gmail API.

Commands:
  'triage'   → fetch + classify + prioritize unread emails
  'draft'    → generate smart reply draft for email
  'send'     → send email (requires human approval in non-auto mode)
  'summary'  → daily email digest → Telegram
  'watch'    → subscribe to Gmail push notifications
  'pipeline' → full auto: triage → draft replies → Telegram digest

Architecture:
  GmailManager (skills/gmail/) → OAuth2 + Gmail API (read/write)
  LLMRouter → classification + draft generation
  RAGEngine → context from previous emails (anti-repetition)

Priority levels:
  CRITICAL  → action required today (deadline, invoice, legal)
  HIGH      → needs reply within 24h
  MEDIUM    → informational, reply within 48h
  LOW       → newsletter, FYI, no reply needed
  SPAM      → unsubscribe candidate
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.agent_base import AgentBase, TaskResult
from core.observability.decorators import observe_agent
from agents.llm import LLMRouter


@dataclass
class EmailSummary:
    """Structured summary of a single email."""
    message_id: str
    subject: str
    sender: str
    received_at: str
    snippet: str
    priority: str           # CRITICAL | HIGH | MEDIUM | LOW | SPAM
    category: str           # work | personal | finance | newsletter | notification
    action_required: bool
    suggested_reply: str = ""
    labels: list = field(default_factory=list)
    thread_id: str = ""


@observe_agent
class GmailAgent(AgentBase):
    """
    Intelligent Gmail automation.
    Zero cost: Gmail API free tier (1B quota units/day).
    """

    AGENT_ID = "gmail"

    # Priority → emoji mapping for Telegram reports
    PRIORITY_EMOJI = {
        "CRITICAL": "🚨",
        "HIGH":     "🔴",
        "MEDIUM":   "🟡",
        "LOW":      "🟢",
        "SPAM":     "⛔",
    }

    TRIAGE_DATA_PATH = Path("data/gmail/triage_cache.json")

    def __init__(self):
        super().__init__()
        self.llm = LLMRouter()
        self.logger = logging.getLogger(self.__class__.__name__)
        Path("data/gmail").mkdir(parents=True, exist_ok=True)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute GmailAgent command.
        kwargs:
            max_emails (int): max emails to process (default 20)
            dry_run (bool): skip send/draft operations
            notify_telegram (bool): send Telegram digest (default True)
            message_id (str): target email for draft/reply
            priority_filter (str): only process emails >= this priority
        """
        start = asyncio.get_event_loop().time()
        cmd = task.lower().strip()

        try:
            if cmd == "pipeline":
                return await self._run_pipeline(kwargs, start)
            elif cmd == "triage":
                return await self._triage_inbox(kwargs, start)
            elif cmd == "draft":
                return await self._generate_draft(kwargs, start)
            elif cmd == "summary":
                return await self._generate_digest(kwargs, start)
            elif cmd == "send":
                return await self._send_email(kwargs, start)
            elif cmd == "watch":
                return await self._setup_watch(kwargs, start)
            else:
                return TaskResult(
                    success=False,
                    error=(
                        f"Unknown command: '{cmd}'. "
                        "Valid: pipeline, triage, draft, summary, send, watch"
                    )
                )
        except Exception as e:
            self.logger.error(f"GmailAgent error: {e}", exc_info=True)
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _run_pipeline(self, kwargs: dict, start: float) -> TaskResult:
        """Full pipeline: fetch → triage → draft criticals → Telegram digest."""
        pipeline_data = {"steps": [], "timestamp": datetime.now().isoformat()}

        # Step 1: Triage inbox
        triage_result = await self._triage_inbox(kwargs, start)
        if not triage_result.success:
            return triage_result

        emails = triage_result.data.get("emails", [])
        pipeline_data["total_processed"] = len(emails)
        pipeline_data["by_priority"] = triage_result.data.get("by_priority", {})
        pipeline_data["steps"].append("triage")

        # Step 2: Auto-draft replies for CRITICAL + HIGH
        drafts_created = 0
        if not kwargs.get("dry_run", False):
            criticals = [e for e in emails
                         if e.priority in ("CRITICAL", "HIGH")
                         and e.action_required]
            for email in criticals[:3]:  # cap at 3 to save LLM quota
                draft = await self._draft_for_email(email)
                if draft:
                    email.suggested_reply = draft
                    drafts_created += 1

        pipeline_data["drafts_created"] = drafts_created
        if drafts_created:
            pipeline_data["steps"].append("drafted")

        # Step 3: Telegram digest
        if kwargs.get("notify_telegram", True) and not kwargs.get("dry_run", False):
            await self._send_telegram_digest(emails, pipeline_data)
            pipeline_data["steps"].append("telegram_notified")

        # Step 4: RAG index important emails
        await self._index_emails_to_rag(emails)
        pipeline_data["steps"].append("rag_indexed")

        return TaskResult(
            success=True,
            data={
                **pipeline_data,
                "emails": [self._email_to_dict(e) for e in emails],
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _triage_inbox(self, kwargs: dict, start: float) -> TaskResult:
        """Fetch and classify unread emails."""
        max_emails = kwargs.get("max_emails", 20)
        raw_emails = await self._fetch_emails(max_emails)

        if not raw_emails:
            return TaskResult(
                success=True,
                data={
                    "emails": [],
                    "by_priority": {},
                    "message": "Inbox empty or Gmail not configured",
                },
                execution_time=asyncio.get_event_loop().time() - start
            )

        # Classify emails concurrently (batch of 5 to avoid rate limits)
        classified = []
        for i in range(0, len(raw_emails), 5):
            batch = raw_emails[i:i+5]
            batch_results = await asyncio.gather(
                *[self._classify_email(e) for e in batch],
                return_exceptions=True,
            )
            for result in batch_results:
                if isinstance(result, EmailSummary):
                    classified.append(result)

        # Group by priority
        by_priority = {}
        for e in classified:
            by_priority[e.priority] = by_priority.get(e.priority, 0) + 1

        # Apply priority filter
        priority_filter = kwargs.get("priority_filter")
        priority_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "SPAM"]
        if priority_filter and priority_filter in priority_order:
            min_idx = priority_order.index(priority_filter)
            classified = [
                e for e in classified
                if priority_order.index(e.priority) <= min_idx
            ]

        # Sort: CRITICAL first
        classified.sort(
            key=lambda e: priority_order.index(e.priority)
        )

        return TaskResult(
            success=True,
            data={
                "emails": classified,
                "by_priority": by_priority,
                "total": len(classified),
                "action_required": sum(
                    1 for e in classified if e.action_required
                ),
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _generate_draft(self, kwargs: dict, start: float) -> TaskResult:
        """Generate a draft reply for a specific email."""
        message_id = kwargs.get("message_id", "")
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        sender = kwargs.get("sender", "")

        if not (message_id or body):
            return TaskResult(
                success=False,
                error="'message_id' or 'body' kwarg required"
            )

        # Create a minimal EmailSummary for drafting
        email = EmailSummary(
            message_id=message_id,
            subject=subject,
            sender=sender,
            received_at=datetime.now().isoformat(),
            snippet=body[:300],
            priority="HIGH",
            category="work",
            action_required=True,
        )
        draft = await self._draft_for_email(email)
        return TaskResult(
            success=bool(draft),
            data={"draft": draft, "message_id": message_id},
            error=None if draft else "Draft generation returned empty",
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _generate_digest(self, kwargs: dict, start: float) -> TaskResult:
        """Generate daily email digest and optionally send to Telegram."""
        triage = await self._triage_inbox(kwargs, start)
        if not triage.success:
            return triage

        emails = triage.data.get("emails", [])
        if kwargs.get("notify_telegram", True) and not kwargs.get("dry_run", False):
            await self._send_telegram_digest(emails, triage.data)

        return TaskResult(
            success=True,
            data={
                "digest": self._build_digest_text(emails),
                "by_priority": triage.data.get("by_priority", {}),
                "total": len(emails),
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _send_email(self, kwargs: dict, start: float) -> TaskResult:
        """Send an email (requires dry_run=False + proper credentials)."""
        if kwargs.get("dry_run", True):
            return TaskResult(
                success=True,
                data={"message": "dry_run=True — email not sent"},
            )
        try:
            gmail = self._get_gmail_manager()
            to = kwargs.get("to", "")
            subject = kwargs.get("subject", "")
            body = kwargs.get("body", "")

            if not all([to, subject, body]):
                return TaskResult(
                    success=False,
                    error="'to', 'subject', 'body' required for send command"
                )

            result = await gmail.execute({
                "action": "send_email",
                "to": [to],
                "subject": subject,
                "body": body,
            })
            return TaskResult(
                success=result.get("success", False),
                data={"sent_to": to, "subject": subject, "result": str(result)},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _setup_watch(self, kwargs: dict, start: float) -> TaskResult:
        """Setup Gmail push notifications (requires Pub/Sub topic)."""
        return TaskResult(
            success=True,
            data={
                "message": (
                    "Gmail Watch requires Google Cloud Pub/Sub configuration. "
                    "Use polling via AutonomousLoop instead: "
                    "LoopTask(agent_id='gmail', task='pipeline', interval=3600)"
                )
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    # ── Internal helpers ──────────────────────────────────────

    def _get_gmail_manager(self):
        """Get GmailManager instance."""
        try:
            from skills.gmail.manager import GmailManager
            return GmailManager()
        except ImportError as e:
            raise ImportError(
                f"GmailManager not found in skills/gmail/ — {e}"
            )

    async def _fetch_emails(self, max_emails: int) -> list:
        """Fetch unread emails via GmailManager."""
        try:
            gmail = self._get_gmail_manager()
            result = await gmail.execute({
                "action": "list_unread",
                "limit": max_emails,
            })
            if result.get("success"):
                return result.get("emails", [])
            self.logger.warning(f"Gmail fetch failed: {result.get('error')}")
            return []
        except Exception as e:
            self.logger.warning(f"Gmail fetch failed: {e}")
            return []

    async def _classify_email(self, raw: dict) -> EmailSummary:
        """Classify a single email using LLM."""
        subject = raw.get("subject", raw.get("Subject", ""))
        sender = raw.get("from_address", raw.get("from", raw.get("From", "")))
        snippet = raw.get("body_plain", raw.get("snippet", ""))[:400]
        message_id = str(raw.get("id", raw.get("message_id", "")))
        thread_id = str(raw.get("threadId", raw.get("thread_id", "")))

        prompt = f"""Classify this email and respond ONLY with valid JSON:

Subject: {subject}
From: {sender}
Preview: {snippet}

JSON format:
{{
  "priority": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW"|"SPAM",
  "category": "work"|"personal"|"finance"|"newsletter"|"notification",
  "action_required": true|false,
  "reasoning": "one sentence"
}}

Rules:
- CRITICAL: deadline today, invoice overdue, legal/legal notice
- HIGH: needs reply in 24h, meeting request, client message
- MEDIUM: FYI, reply in 48h OK
- LOW: newsletters, receipts, no action needed
- SPAM: bulk email, unsubscribe candidate
Respond ONLY with JSON:"""

        try:
            response = await self.llm.complete(prompt, task_type="fast")
            s = response.find("{")
            e = response.rfind("}") + 1
            if s >= 0 and e > s:
                data = json.loads(response[s:e])
                return EmailSummary(
                    message_id=message_id,
                    subject=subject,
                    sender=sender,
                    received_at=raw.get("date", raw.get("internalDate", "")),
                    snippet=snippet,
                    priority=data.get("priority", "MEDIUM"),
                    category=data.get("category", "work"),
                    action_required=data.get("action_required", False),
                    thread_id=thread_id,
                )
        except Exception as e:
            self.logger.warning(f"Classification failed for '{subject}': {e}")

        # Fallback: rule-based classification
        return self._rule_based_classify(
            message_id, subject, sender, snippet, thread_id
        )

    def _rule_based_classify(
        self, msg_id: str, subject: str, sender: str,
        snippet: str, thread_id: str
    ) -> EmailSummary:
        """Fallback rule-based classifier (no LLM needed)."""
        subject_lower = subject.lower()
        snippet_lower = snippet.lower()

        # SPAM signals
        spam_signals = ["unsubscribe", "newsletter", "promo", "oferta",
                        "desconto", "click here", "clique aqui"]
        # CRITICAL signals
        critical_signals = ["urgente", "urgent", "prazo", "deadline",
                            "fatura vencida", "overdue", "legal notice"]
        # HIGH signals
        high_signals = ["reunião", "meeting", "reply", "responda",
                        "preciso", "confirme", "prazo"]

        text = f"{subject_lower} {snippet_lower}"

        if any(s in text for s in spam_signals):
            priority, action = "SPAM", False
        elif any(s in text for s in critical_signals):
            priority, action = "CRITICAL", True
        elif any(s in text for s in high_signals):
            priority, action = "HIGH", True
        else:
            priority, action = "MEDIUM", False

        return EmailSummary(
            message_id=msg_id,
            subject=subject,
            sender=sender,
            received_at=datetime.now().isoformat(),
            snippet=snippet,
            priority=priority,
            category="work",
            action_required=action,
            thread_id=thread_id,
        )

    async def _draft_for_email(self, email: EmailSummary) -> str:
        """Generate a draft reply using LLM."""
        prompt = f"""Write a professional reply in Brazilian Portuguese to this email.

From: {email.sender}
Subject: {email.subject}
Email content: {email.snippet}

Guidelines:
- Concise (3-5 sentences max)
- Professional but warm tone
- Address the main point directly
- Sign as: "Johnathan" (no last name)
- Do NOT include subject line, just the reply body

Reply:"""

        try:
            return await self.llm.complete(prompt, task_type="fast")
        except Exception as e:
            self.logger.warning(f"Draft generation failed: {e}")
            return ""

    def _build_digest_text(self, emails: list) -> str:
        """Build a plain text email digest."""
        if not emails:
            return "📬 Inbox limpa — nenhum email não lido."

        lines = [f"📬 *Resumo do Inbox* — {len(emails)} emails\n"]
        priority_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "SPAM"]

        for priority in priority_order:
            group = [e for e in emails if e.priority == priority]
            if not group:
                continue
            emoji = self.PRIORITY_EMOJI[priority]
            lines.append(f"\n{emoji} *{priority}* ({len(group)})")
            for e in group[:5]:
                action = "⚡" if e.action_required else " "
                lines.append(f"  {action} {e.subject[:50]} — _{e.sender[:30]}_")
            if len(group) > 5:
                lines.append(f"  ... e mais {len(group) - 5}")

        return "\n".join(lines)

    async def _send_telegram_digest(self, emails: list, data: dict) -> None:
        """Send email digest via Telegram."""
        try:
            digest = self._build_digest_text(emails)
            from telegram.bot import send_notification
            await send_notification(digest)
        except Exception as e:
            self.logger.debug(f"Telegram digest skipped: {e}")

    async def _index_emails_to_rag(self, emails: list) -> None:
        """Index important emails into RAG for context."""
        try:
            from core.rag import RAGEngine
            rag = RAGEngine()
            important = [e for e in emails
                         if e.priority in ("CRITICAL", "HIGH")]
            for e in important:
                await rag.index_document(
                    content=f"{e.subject}: {e.snippet}",
                    metadata={
                        "type": "email",
                        "priority": e.priority,
                        "sender": e.sender,
                        "action_required": e.action_required,
                        "date": e.received_at,
                    },
                    collection="gmail_history",
                )
        except Exception as e:
            self.logger.debug(f"RAG email indexing skipped: {e}")

    def _email_to_dict(self, e: EmailSummary) -> dict:
        """Convert EmailSummary to serializable dict."""
        from dataclasses import asdict
        return asdict(e)
