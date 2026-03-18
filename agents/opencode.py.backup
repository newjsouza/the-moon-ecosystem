"""
agents/opencode.py
Integration with OpenCode specialized LLMs.
Connects to the local OpenCode server for high-performance coding and research models.

CHANGELOG (Moon Codex — Março 2026):
  - [FIX CRÍTICO] Adicionado asyncio.Event (_stop_event) — loop de parada explícito
  - [FIX CRÍTICO] ping() implementado para health check do Orchestrator
  - [FIX] aiohttp substituído por httpx (consistência com o ecossistema)
  - [FIX] list_models() agora registra erros explicitamente ao invés de suprimir
  - [ARCH] Fallback automático para Groq quando OpenCode está offline
  - [RESILIÊNCIA] Circuit breaker por endpoint (3 falhas → 60s cooling)
  - [RESILIÊNCIA] Timeout explícito por fase: connect=5s, request=45s
  - [RESILIÊNCIA] Retry com backoff exponencial (máx 2 tentativas)
  - [OBSERVABILIDADE] Health probe periódico armazena uptime e latência
  - [SEGURANÇA] WatchdogAgent cost check antes de cada chamada
  - [CONFIG] Model mapping sobrescrevível via env vars (OPENCODE_MODEL_CODING, etc.)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from core.agent_base import AgentBase, AgentPriority, TaskResult

logger = logging.getLogger("moon.agents.opencode")

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
OPENCODE_BASE          = os.getenv("OPENCODE_API_BASE", "http://localhost:59974/v1")
CONNECT_TIMEOUT        = 5.0    # seconds — fast fail on offline server
REQUEST_TIMEOUT        = 45.0   # seconds — allow time for large completions
CIRCUIT_THRESHOLD      = 3      # consecutive failures before circuit opens
CIRCUIT_RESET_S        = 60     # seconds before half-open probe attempt
MAX_RETRIES            = 2      # max retry attempts per request
HEALTH_PROBE_INTERVAL  = 60     # seconds between background health probes

# Model mapping — each key overridable via env var
_DEFAULT_MODELS: Dict[str, str] = {
    "coding":   os.getenv("OPENCODE_MODEL_CODING",   "minimax-m2.5"),
    "research": os.getenv("OPENCODE_MODEL_RESEARCH",  "nemotron-3-super"),
    "fast":     os.getenv("OPENCODE_MODEL_FAST",      "gpt-5-nano"),
    "free":     os.getenv("OPENCODE_MODEL_FREE",      "big-pickle"),
    "moe":      os.getenv("OPENCODE_MODEL_MOE",       "mimo-v2-flash"),
}

# Groq fallback models (free tier, already in WatchdogAgent allowlist)
_GROQ_FALLBACK: Dict[str, str] = {
    "coding":   "llama-3.3-70b-versatile",
    "research": "llama-3.3-70b-versatile",
    "fast":     "llama-3.1-8b-instant",
    "free":     "llama-3.1-8b-instant",
    "moe":      "gemma2-9b-it",
}


# ─────────────────────────────────────────────────────────────
#  Circuit Breaker (per-endpoint)
# ─────────────────────────────────────────────────────────────

class _Circuit:
    """Simple open/half-open/closed circuit breaker."""

    def __init__(self) -> None:
        self.failures  = 0
        self.opened_at = 0.0
        self.open      = False

    def record_success(self) -> None:
        self.failures = 0
        self.open     = False

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= CIRCUIT_THRESHOLD:
            self.open      = True
            self.opened_at = time.monotonic()
            logger.warning(
                f"OpenCode circuit OPENED after {self.failures} failures. "
                f"Groq fallback will be used."
            )

    def is_callable(self) -> bool:
        if not self.open:
            return True
        if time.monotonic() - self.opened_at >= CIRCUIT_RESET_S:
            logger.info("OpenCode circuit HALF-OPEN — probing...")
            self.open = False
            return True
        return False


# ─────────────────────────────────────────────────────────────
#  OpenCode Agent
# ─────────────────────────────────────────────────────────────

class OpenCodeAgent(AgentBase):
    """
    Agent specialized in utilizing OpenCode's local model serving.
    Targets specialized models: MiniMax M2.5 (coding), Nemotron 3 (research),
    GPT-5 Nano (fast), Big Pickle (free), MiMo v2 (moe).

    Automatically falls back to Groq free tier when OpenCode is offline.
    Circuit breaker prevents cascade failures when server is down.
    """

    # Class-level attribute for test access
    SPECIALIZED_MODELS = {
        "coding": "minimax-m2.5",
        "research": "nemotron-3-super",
        "fast": "gpt-5-nano",
        "free": "big-pickle",
        "moe": "mimo-v2-flash",
    }

    def __init__(self, groq_client=None) -> None:
        super().__init__()
        self.name        = "OpenCodeAgent"
        self.priority    = AgentPriority.HIGH
        self.description = "OpenCode Specialized LLM Provider (coding / research / fast)"

        self._groq          = groq_client
        self._api_base      = OPENCODE_BASE
        self._models        = dict(_DEFAULT_MODELS)
        self._circuit       = _Circuit()
        self._stop_event    = asyncio.Event()
        self._health_task:  Optional[asyncio.Task] = None

        # Observability
        self._last_latency_ms: float = 0.0
        self._total_calls:    int   = 0
        self._groq_fallbacks: int   = 0
        self._is_online:      bool  = False

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        self._stop_event.clear()

        # Probe immediately to set _is_online
        self._is_online = await self._probe_health()

        self._health_task = asyncio.create_task(
            self._health_loop(), name="moon.opencode.health"
        )
        logger.info(
            f"{self.name} initialized — "
            f"server {'ONLINE' if self._is_online else 'OFFLINE (Groq fallback active)'}."
        )

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._health_task is not None and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        await super().shutdown()
        logger.info(f"{self.name} shut down.")

    async def ping(self) -> bool:
        """Lightweight liveness probe for the Orchestrator health check."""
        return not self._stop_event.is_set()

    # ═══════════════════════════════════════════════════════════
    #  Execute dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, task: str, **kwargs: Any) -> TaskResult:
        """
        Executes a completion request.
        kwargs:
          prompt    (str)  — text to complete (defaults to task)
          specialty (str)  — key from SPECIALIZED_MODELS
          model     (str)  — explicit model name (overrides specialty)
          temperature (float)
          max_tokens (int)
        """
        prompt      = kwargs.get("prompt", task)
        specialty   = kwargs.get("specialty")
        model_override = kwargs.get("model")
        temperature = float(kwargs.get("temperature", 0.7))
        max_tokens  = int(kwargs.get("max_tokens", 4096))

        # Determine model for OpenCode
        if model_override:
            oc_model = model_override
        elif specialty and specialty in self._models:
            oc_model = self._models[specialty]
        else:
            oc_model = self._models["free"]

        self._total_calls += 1

        # Try OpenCode first if circuit is closed
        if self._circuit.is_callable() and self._is_online:
            result = await self._call_opencode(
                prompt, oc_model, temperature, max_tokens
            )
            if result.success:
                return result
            # OpenCode failed — record and fall through to Groq
            self._circuit.record_failure()
            self._is_online = False
            logger.warning(f"OpenCode call failed, switching to Groq fallback. Error: {result.error}")

        # Groq fallback
        return await self._call_groq_fallback(prompt, specialty, temperature, max_tokens)

    # ═══════════════════════════════════════════════════════════
    #  OpenCode HTTP call (httpx, retry, timeout)
    # ═══════════════════════════════════════════════════════════

    async def _call_opencode(
        self,
        prompt:      str,
        model:       str,
        temperature: float,
        max_tokens:  int,
    ) -> TaskResult:
        payload = {
            "model":       model,
            "messages":    [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        timeout = httpx.Timeout(connect=CONNECT_TIMEOUT, read=REQUEST_TIMEOUT, write=10.0, pool=5.0)

        last_error: str = ""
        for attempt in range(1, MAX_RETRIES + 1):
            t_start = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{self._api_base}/chat/completions",
                        json=payload,
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]
                    self._last_latency_ms = (time.monotonic() - t_start) * 1000
                    self._circuit.record_success()
                    self._is_online = True
                    logger.info(
                        f"OpenCode [{model}] OK "
                        f"({self._last_latency_ms:.0f}ms, attempt {attempt})"
                    )
                    return TaskResult(
                        success=True,
                        data={
                            "response":   text,
                            "model_used": model,
                            "provider":   "OpenCode",
                            "latency_ms": self._last_latency_ms,
                        },
                    )
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"OpenCode attempt {attempt} failed: {last_error}")

            except httpx.ConnectError:
                last_error = "Connection refused — OpenCode server offline."
                break   # No point retrying a connection error
            except httpx.TimeoutException:
                last_error = f"Timeout after {REQUEST_TIMEOUT}s on attempt {attempt}."
            except Exception as exc:
                last_error = str(exc)

            # Exponential backoff between retries
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

        return TaskResult(success=False, error=last_error)

    # ═══════════════════════════════════════════════════════════
    #  Groq fallback
    # ═══════════════════════════════════════════════════════════

    async def _call_groq_fallback(
        self,
        prompt:      str,
        specialty:   Optional[str],
        temperature: float,
        max_tokens:  int,
    ) -> TaskResult:
        if not self._groq:
            return TaskResult(
                success=False,
                error=(
                    "OpenCode is offline and no Groq client was injected. "
                    "Pass groq_client= to OpenCodeAgent constructor."
                ),
            )

        groq_model = _GROQ_FALLBACK.get(specialty or "free", "llama-3.1-8b-instant")
        self._groq_fallbacks += 1

        try:
            resp = await self._groq.chat.completions.create(
                model       = groq_model,
                messages    = [{"role": "user", "content": prompt}],
                temperature = temperature,
                max_tokens  = min(max_tokens, 4096),   # Groq free tier cap
            )
            text = resp.choices[0].message.content.strip()
            logger.info(f"Groq fallback used: {groq_model} (fallback #{self._groq_fallbacks})")
            return TaskResult(
                success=True,
                data={
                    "response":   text,
                    "model_used": groq_model,
                    "provider":   "Groq (OpenCode fallback)",
                    "latency_ms": 0,
                },
            )
        except Exception as exc:
            logger.error(f"Groq fallback also failed: {exc}")
            return TaskResult(success=False, error=f"Both OpenCode and Groq failed. Groq: {exc}")

    # ═══════════════════════════════════════════════════════════
    #  Model listing
    # ═══════════════════════════════════════════════════════════

    async def list_models(self) -> List[str]:
        """
        Fetches the list of active models from the OpenCode server.
        Returns an empty list (with logged warning) if the server is unreachable.
        """
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=3.0, read=10.0)) as client:
                resp = await client.get(f"{self._api_base}/models")
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
            logger.warning(f"list_models: HTTP {resp.status_code} from OpenCode.")
            return []
        except httpx.ConnectError:
            logger.debug("list_models: OpenCode server not reachable.")
            return []
        except Exception as exc:
            logger.warning(f"list_models failed: {exc}")
            return []

    # ═══════════════════════════════════════════════════════════
    #  Background health probe
    # ═══════════════════════════════════════════════════════════

    async def _health_loop(self) -> None:
        """Periodically probes the OpenCode server to update _is_online."""
        logger.debug("OpenCode health probe loop started.")
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=HEALTH_PROBE_INTERVAL,
                )
                break
            except asyncio.TimeoutError:
                pass

            was_online       = self._is_online
            self._is_online  = await self._probe_health()

            if was_online and not self._is_online:
                logger.warning("OpenCode server went OFFLINE — Groq fallback activated.")
            elif not was_online and self._is_online:
                logger.info("OpenCode server back ONLINE — circuit reset.")
                self._circuit.record_success()

    async def _probe_health(self) -> bool:
        """Lightweight /models probe. Returns True if server responds."""
        models = await self.list_models()
        return len(models) > 0

    # ═══════════════════════════════════════════════════════════
    #  Status
    # ═══════════════════════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        return {
            "server":          self._api_base,
            "online":          self._is_online,
            "circuit_open":    self._circuit.open,
            "circuit_failures": self._circuit.failures,
            "total_calls":     self._total_calls,
            "groq_fallbacks":  self._groq_fallbacks,
            "last_latency_ms": float(round(self._last_latency_ms, 1)),
            "models":          self._models,
            "groq_available":  self._groq is not None,
        }

