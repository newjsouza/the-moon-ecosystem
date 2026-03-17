"""tests/test_browser_pilot.py — Testes unitários do BrowserPilot"""
import pytest
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN",   "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID",      "123456")
os.environ.setdefault("GROQ_API_KEY",          "test_key")
os.environ.setdefault("FOOTBALL_DATA_API_KEY", "test_key")

from agents.browser_pilot import BrowserPilot, BrowserStep, PilotSession, PilotNotifier


class TestBrowserStep:

    def test_from_dict_basic(self):
        step = BrowserStep.from_dict({
            "action": "goto",
            "value": "https://example.com",
            "description": "Vai para example"
        })
        assert step.action == "goto"
        assert step.value  == "https://example.com"
        assert step.sensitive is False

    def test_from_dict_sensitive_by_action(self):
        step = BrowserStep.from_dict({
            "action": "fill_sensitive",
            "selector": "#pass",
            "label": "Senha"
        })
        assert step.sensitive is True

    def test_from_dict_sensitive_by_keyword(self):
        step = BrowserStep.from_dict({
            "action": "fill",
            "selector": "#password",
            "value": ""
        })
        assert step.sensitive is True

    def test_from_dict_optional(self):
        step = BrowserStep.from_dict({
            "action": "click",
            "selector": ".close",
            "optional": True
        })
        assert step.optional is True

    def test_sensitive_keywords_detection(self):
        for keyword in ["password", "senha", "token", "otp", "cvv"]:
            step = BrowserStep.from_dict({
                "action": "fill",
                "selector": f"#{keyword}_field"
            })
            assert step.sensitive is True, f"Keyword '{keyword}' não detectado como sensível"


class TestBrowserPilot:

    def test_init(self):
        pilot = BrowserPilot()
        assert pilot._sessions == {}
        assert pilot._bridge is None

    def test_get_active_session_empty(self):
        pilot = BrowserPilot()
        assert pilot.get_active_session() is None

    @pytest.mark.asyncio
    async def test_provide_input_no_session(self):
        pilot  = BrowserPilot()
        result = await pilot.provide_sensitive_input("inexistente", "valor")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_session_not_found(self):
        pilot  = BrowserPilot()
        result = await pilot.cancel_session("inexistente")
        assert result is False

    @pytest.mark.asyncio
    async def test_start_session_no_bridge_graceful(self):
        """Verifica que start_session falha graciosamente sem bridge."""
        pilot = BrowserPilot()

        # Mock do planner para retornar steps
        pilot.planner.generate = AsyncMock(return_value=[
            BrowserStep.from_dict({
                "action": "goto",
                "value": "https://example.com",
                "description": "Teste"
            })
        ])
        # Mock do notifier para não enviar ao Telegram real
        pilot.notifier.send_text  = AsyncMock(return_value=True)
        pilot.notifier.send_photo = AsyncMock(return_value=True)
        pilot.notifier.notify_step = AsyncMock(return_value=None)
        pilot.notifier.notify_error = AsyncMock(return_value=None)
        pilot.notifier.notify_done  = AsyncMock(return_value=None)

        session_id = await pilot.start_session("teste sem bridge")
        assert session_id.startswith("pilot_")
        # Aguarda task em background
        await asyncio.sleep(0.3)


class TestPilotNotifier:

    @pytest.mark.asyncio
    async def test_send_text_no_token(self):
        import agents.browser_pilot as mod
        original_token   = mod.TELEGRAM_BOT_TOKEN
        original_chat_id = mod.TELEGRAM_CHAT_ID
        mod.TELEGRAM_BOT_TOKEN = ""
        mod.TELEGRAM_CHAT_ID   = ""

        notifier = PilotNotifier()
        notifier.token   = ""
        notifier.chat_id = ""
        result = await notifier.send_text("teste")
        assert result is False

        mod.TELEGRAM_BOT_TOKEN = original_token
        mod.TELEGRAM_CHAT_ID   = original_chat_id

    @pytest.mark.asyncio
    async def test_request_sensitive_input_no_screenshot(self):
        notifier = PilotNotifier()
        notifier.send_text  = AsyncMock(return_value=True)
        notifier.send_photo = AsyncMock(return_value=True)
        await notifier.request_sensitive_input("Senha", "Preencher senha", None)
        notifier.send_text.assert_called_once()
        # Sem screenshot → usa send_text
        notifier.send_photo.assert_not_called()


class TestPilotSession:

    def test_session_creation(self):
        session = PilotSession(
            session_id="test_123",
            task="Teste de navegação",
            steps=[
                BrowserStep.from_dict({
                    "action": "goto",
                    "value": "https://example.com",
                    "description": "Ir para example"
                })
            ]
        )
        assert session.session_id == "test_123"
        assert session.status == "running"
        assert session.current_step == 0
        assert len(session.steps) == 1

    def test_session_with_sensitive_step(self):
        session = PilotSession(
            session_id="test_456",
            task="Login",
            steps=[
                BrowserStep.from_dict({
                    "action": "fill_sensitive",
                    "selector": "#password",
                    "label": "Senha",
                    "sensitive": True,
                    "description": "Preencher senha"
                })
            ]
        )
        assert session.steps[0].sensitive is True
        assert session.steps[0].label == "Senha"
