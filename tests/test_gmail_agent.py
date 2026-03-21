"""
Tests for GmailAgent — zero network calls, zero API key required.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestEmailSummary:

    def test_import(self):
        from agents.gmail_agent import EmailSummary
        e = EmailSummary(
            message_id="001", subject="Test", sender="test@test.com",
            received_at="2026-03-21", snippet="Hello", priority="HIGH",
            category="work", action_required=True
        )
        assert e.priority == "HIGH"
        assert e.action_required is True

    def test_default_labels(self):
        from agents.gmail_agent import EmailSummary
        e = EmailSummary(
            message_id="002", subject="X", sender="x@x.com",
            received_at="", snippet="", priority="LOW",
            category="newsletter", action_required=False
        )
        assert e.labels == []
        assert e.suggested_reply == ""


class TestGmailAgentCommands:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_import(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        assert agent.AGENT_ID == "gmail"

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        result = await agent._execute("invalid_cmd")
        assert result.success is False
        assert "Unknown command" in result.error

    @pytest.mark.asyncio
    async def test_triage_empty_inbox(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        with patch.object(agent, "_fetch_emails",
                          new_callable=AsyncMock,
                          return_value=[]):
            result = await agent._execute("triage", max_emails=10)
        assert result.success is True
        assert result.data["emails"] == []

    @pytest.mark.asyncio
    async def test_triage_classifies_emails(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()

        mock_emails = [
            {"id": "001", "subject": "URGENTE: prazo amanhã",
             "from_address": "cliente@empresa.com", "body_plain": "Precisa ser entregue"},
            {"id": "002", "subject": "Newsletter semanal",
             "from_address": "news@newsletter.com", "body_plain": "Unsubscribe aqui"},
        ]

        mock_classification = (
            '{"priority": "CRITICAL", "category": "work",'
            '"action_required": true, "reasoning": "Prazo urgente"}'
        )

        with patch.object(agent, "_fetch_emails",
                          new_callable=AsyncMock,
                          return_value=mock_emails), \
             patch.object(agent.llm, "complete",
                          new_callable=AsyncMock,
                          return_value=mock_classification):
            result = await agent._execute("triage", max_emails=10)

        assert result.success is True
        assert result.data["total"] > 0

    @pytest.mark.asyncio
    async def test_draft_requires_message_or_body(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        result = await agent._execute("draft")
        assert result.success is False
        assert "required" in result.error

    @pytest.mark.asyncio
    async def test_draft_generates_reply(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        mock_reply = "Olá, obrigado pelo contato. Respondendo em breve. Johnathan"
        with patch.object(agent.llm, "complete",
                          new_callable=AsyncMock,
                          return_value=mock_reply):
            result = await agent._execute(
                "draft",
                message_id="001",
                subject="Reunião amanhã",
                sender="cliente@empresa.com",
                body="Podemos marcar reunião amanhã às 15h?"
            )
        assert result.success is True
        assert result.data["draft"] == mock_reply

    @pytest.mark.asyncio
    async def test_send_dry_run(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        result = await agent._execute(
            "send",
            dry_run=True,
            to="test@test.com",
            subject="Test",
            body="Test body"
        )
        assert result.success is True
        assert "dry_run" in result.data["message"]

    @pytest.mark.asyncio
    async def test_watch_returns_instructions(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        result = await agent._execute("watch")
        assert result.success is True
        assert "Pub/Sub" in result.data["message"] or \
               "AutonomousLoop" in result.data["message"]

    @pytest.mark.asyncio
    async def test_summary_dry_run(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        with patch.object(agent, "_fetch_emails",
                          new_callable=AsyncMock,
                          return_value=[]):
            result = await agent._execute(
                "summary",
                dry_run=True,
                notify_telegram=False
            )
        assert result.success is True
        assert "by_priority" in result.data

    @pytest.mark.asyncio
    async def test_pipeline_dry_run_empty_inbox(self):
        from agents.gmail_agent import GmailAgent
        agent = GmailAgent()
        with patch.object(agent, "_fetch_emails",
                          new_callable=AsyncMock,
                          return_value=[]):
            result = await agent._execute(
                "pipeline",
                dry_run=True,
                notify_telegram=False
            )
        assert result.success is True
        assert "steps" in result.data
        assert "triage" in result.data["steps"]


class TestRuleBasedClassifier:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        from agents.gmail_agent import GmailAgent
        self.agent = GmailAgent()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_spam_detected(self):
        e = self.agent._rule_based_classify(
            "001", "Newsletter - Unsubscribe", "news@promo.com",
            "Clique aqui para ofertas", ""
        )
        assert e.priority == "SPAM"
        assert e.action_required is False

    def test_critical_detected(self):
        e = self.agent._rule_based_classify(
            "002", "URGENTE: fatura vencida", "banco@email.com",
            "Sua fatura está vencida há 3 dias", ""
        )
        assert e.priority == "CRITICAL"
        assert e.action_required is True

    def test_high_detected(self):
        e = self.agent._rule_based_classify(
            "003", "Reunião amanhã às 15h", "cliente@empresa.com",
            "Confirme sua presença na reunião", ""
        )
        assert e.priority == "HIGH"

    def test_medium_fallback(self):
        e = self.agent._rule_based_classify(
            "004", "Atualização do sistema", "ti@empresa.com",
            "O sistema foi atualizado com sucesso", ""
        )
        assert e.priority == "MEDIUM"


class TestDigestBuilder:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()
        from agents.gmail_agent import GmailAgent, EmailSummary
        self.agent = GmailAgent()
        self.EmailSummary = EmailSummary

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_empty_inbox_message(self):
        digest = self.agent._build_digest_text([])
        assert "limpa" in digest or "empty" in digest.lower()

    def test_digest_contains_priorities(self):
        emails = [
            self.EmailSummary("001", "Urgente!", "a@a.com", "",
                              "test", "CRITICAL", "work", True),
            self.EmailSummary("002", "Newsletter", "b@b.com", "",
                              "news", "SPAM", "newsletter", False),
        ]
        digest = self.agent._build_digest_text(emails)
        assert "CRITICAL" in digest
        assert "SPAM" in digest

    def test_digest_caps_display(self):
        emails = [
            self.EmailSummary(
                str(i), f"Email {i}", "x@x.com", "",
                "content", "HIGH", "work", False
            )
            for i in range(10)
        ]
        digest = self.agent._build_digest_text(emails)
        assert "mais" in digest or "10" in digest
