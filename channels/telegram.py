"""
channels/telegram.py — Telegram Channel Infrastructure for The Moon.

CHANGELOG (Moon Codex — Março 2026):
  - [FIX CRÍTICO] Conflito de polling eliminado: TelegramChannel agora delega
    ao MoonBot (python-telegram-bot) ao invés de ter loop próprio
  - [FIX] send_message usa httpx async ao invés de subprocess+curl
  - [RESILIÊNCIA] Retry automático com backoff em send_message
  - [RESILIÊNCIA] Markdown fallback: tenta plain text se parse falhar
  - [ARCH] MoonBot é o único loop de polling — este canal apenas envia
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from .base import ChannelBase

load_dotenv()
logger = logging.getLogger("moon.channels.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramChannel(ChannelBase):
    """
    Telegram Channel for The Moon ecosystem.

    Responsabilidade: ENVIAR mensagens proativas do ecossistema
    (alertas, notificações, relatórios do Orchestrator).

    O loop de polling e handling de mensagens do usuário é
    responsabilidade exclusiva do MoonBot (agents/telegram/bot.py).
    Este canal NÃO faz polling — evita conflito de token.
    """

    def __init__(
        self,
        token:   Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        super().__init__(name="telegram")
        self.token   = token   or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._client: Optional[httpx.AsyncClient] = None

    # ════════════════════════════════════════════════════════
    #  Lifecycle
    # ════════════════════════════════════════════════════════

    async def start(self) -> None:
        """Verifies bot token. Does NOT start polling."""
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN not set — channel disabled.")
            return

        self._client = httpx.AsyncClient(timeout=15)

        try:
            resp = await self._api_call("getMe")
            if resp.get("ok"):
                name = resp["result"]["first_name"]
                user = resp["result"]["username"]
                logger.info(f"TelegramChannel: bot identity confirmed — {name} (@{user})")
            else:
                logger.error(f"TelegramChannel: invalid token — {resp}")
        except Exception as exc:
            logger.error(f"TelegramChannel start error: {exc}")

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("TelegramChannel stopped.")

    # ════════════════════════════════════════════════════════
    #  Send message — httpx async with retry + Markdown fallback
    # ════════════════════════════════════════════════════════

    async def send_message(
        self,
        text:         str,
        recipient_id: Optional[str] = None,
        **kwargs:     Any,
    ) -> bool:
        target = recipient_id or self.chat_id
        if not target:
            logger.warning("TelegramChannel.send_message: no recipient_id or chat_id.")
            return False
        if not self.token:
            return False

        # Telegram has 4096 char limit
        if len(text) > 4000:
            text = text[:4000] + "\n\n…(mensagem truncada)"

        # Try with Markdown first, fallback to plain text
        for attempt, parse_mode in enumerate([("Markdown", True), ("", False)], 1):
            mode, use_md = parse_mode
            payload: Dict[str, Any] = {"chat_id": target, "text": text}
            if use_md:
                payload["parse_mode"] = mode

            try:
                resp = await self._api_call("sendMessage", payload)
                if resp.get("ok"):
                    return True

                desc = resp.get("description", "").lower()
                if use_md and ("parse" in desc or "entities" in desc):
                    logger.debug("Markdown parse failed — retrying as plain text.")
                    continue
                else:
                    logger.error(f"sendMessage failed (attempt {attempt}): {resp}")
                    break

            except Exception as exc:
                logger.error(f"sendMessage error (attempt {attempt}): {exc}")
                if attempt == 1:
                    await asyncio.sleep(1)
                    continue
                break

        return False

    # ════════════════════════════════════════════════════════
    #  Internal API helper
    # ════════════════════════════════════════════════════════

    async def _api_call(
        self,
        method:  str,
        payload: Optional[Dict] = None,
        timeout: int = 10,
    ) -> dict:
        url = TELEGRAM_API_BASE.format(token=self.token, method=method)
        client = self._client or httpx.AsyncClient(timeout=timeout)
        try:
            if payload:
                resp = await client.post(url, json=payload, timeout=timeout)
            else:
                resp = await client.get(url, timeout=timeout)
            return resp.json()
        except Exception as exc:
            return {"ok": False, "description": str(exc)}
        finally:
            if not self._client:
                await client.aclose()
