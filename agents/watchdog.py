"""
agents/watchdog.py
The Guardian of The Moon: Monitors system health, resources, and cost compliance.

CHANGELOG (Moon Codex — Março 2026):
  - [FIX CRÍTICO] _is_model_free migrado para allowlist (whitelist-first) — antes, qualquer
    modelo não reconhecido passava na checagem. Agora modelos desconhecidos são bloqueados
    por default, evitando execuções acidentais de APIs pagas.
  - [FIX CRÍTICO] "opencode" adicionado à allowlist — o Orchestrator passava esse valor
    e era incorretamente bloqueado pela lógica anterior.
  - [FIX] CPU fallback corrigido para usar os.cpu_count() ao invés de fator fixo de 4 cores.
  - [ARCH] Integração com MessageBus: alertas agora publicados no tópico
    "watchdog.alert" para que o Orchestrator possa reagir programaticamente.
  - [RESILIÊNCIA] Alert deduplication: mesmo alerta não é re-publicado antes de
    ALERT_COOLDOWN segundos (evita flood de logs e mensagens).
  - [RESILIÊNCIA] Loop de monitoramento usa asyncio.Event (_stop_event) ao invés de
    depender de is_initialized — contrato de parada explícito e seguro.
  - [RESILIÊNCIA] Cost accumulator agora funcional: _record_cost() incrementa o
    acumulador e publica alerta se limite diário for ultrapassado.
  - [OBSERVABILIDADE] ping() implementado para suporte ao health check do Orchestrator.
  - [OBSERVABILIDADE] Status expandido: uptime, process count, alert history resumido.
  - [SEGURANÇA] ALLOWED_MODELS e BLOCKED_MODELS separados — blocklist tem precedência,
    allowlist define acesso, desconhecidos são negados com log explícito.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from core.agent_base import AgentBase, AgentPriority, TaskResult

logger = logging.getLogger("moon.agents.watchdog")

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
MONITOR_INTERVAL  = 60    # seconds between health checks
ALERT_COOLDOWN    = 300   # seconds before the same alert can fire again (5 min)
MAX_ALERT_HISTORY = 50    # max entries kept in memory


# ─────────────────────────────────────────────────────────────
#  Model Policy — allowlist-first (unknowns are DENIED)
# ─────────────────────────────────────────────────────────────

# Any substring match → model is FREE to use
_ALLOWED_MODEL_PATTERNS: tuple[str, ...] = (
    # Groq free tier
    "llama",
    "gemma",
    "mixtral",
    "whisper",
    "nemotron",
    "mistral",
    # OpenCode internal routing
    "opencode",
    "minimax",
    "gpt-5-nano",   # OpenCode fast/general (free via OpenCode)
    # Open source / local
    "qwen",
    "deepseek",
    "phi",
    "falcon",
    "bloom",
)

# Any substring match → model is PAID (takes precedence over allowlist)
_BLOCKED_MODEL_PATTERNS: tuple[str, ...] = (
    "gpt-4",
    "gpt-3.5",
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "text-davinci",
    "o1-preview",
    "o1-mini",
)


class WatchdogAgent(AgentBase):
    """
    Systems guardian for The Moon ecosystem.

    Responsibilities:
      - Continuous resource monitoring (CPU / RAM / Disk)
      - Cost-Zero policy enforcement (model allowlist)
      - Alert publishing to MessageBus
      - Alert deduplication to prevent log flooding
      - Uptime and process count tracking
    """

    def __init__(self, message_bus=None) -> None:
        super().__init__()
        self.name = "WatchdogAgent"
        self.description = "Systems guardian: Monitors health, resources, and cost compliance."
        self.priority = AgentPriority.CRITICAL

        # ── Resource thresholds ──────────────────────────────────
        self.max_cpu_percent        = 85.0
        self.max_memory_percent     = 90.0
        self.max_disk_usage_percent = 95.0

        # ── Cost tracking ────────────────────────────────────────
        # Strict Zero Cost Policy: max_daily_cost = 0.0 → any cost is a violation
        self.total_cost_accumulated: float = 0.0
        self.max_daily_cost: float = 0.0

        # ── Observability ────────────────────────────────────────
        self._start_time: float = time.monotonic()
        self._alert_history: List[Dict[str, Any]] = []
        # Maps alert_key → last_triggered timestamp (for deduplication)
        self._alert_last_seen: Dict[str, float] = {}

        # ── MessageBus (optional injection) ─────────────────────
        self._message_bus = message_bus

        # ── Loop control ─────────────────────────────────────────
        self._stop_event = asyncio.Event()
        self._monitoring_task: Optional[asyncio.Task] = None

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        self._stop_event.clear()
        self._monitoring_task = asyncio.create_task(
            self._monitor_loop(), name="moon.watchdog.monitor"
        )
        self._sync_task = asyncio.create_task(
            self._periodic_github_sync(), name="moon.watchdog.github_sync"
        )
        logger.info(f"{self.name} initialized — monitoring active.")

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        await super().shutdown()
        logger.info(f"{self.name} shut down.")

    # ═══════════════════════════════════════════════════════════
    #  ping() — required by Orchestrator health check
    # ═══════════════════════════════════════════════════════════

    async def ping(self) -> bool:
        """Lightweight liveness probe used by the Orchestrator health check."""
        return not self._stop_event.is_set()

    # ═══════════════════════════════════════════════════════════
    #  Execute dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, action: str, **kwargs: Any) -> TaskResult:
        """
        Supported actions:
          status        → Full system metrics snapshot.
          check_cost    → Validate model against Zero-Cost policy (kwargs: model).
          health_check  → Run immediate health check, return list of issues.
          record_cost   → Register a cost event (kwargs: amount, model).
          alert_history → Return recent alert log.
        """
        match action:
            case "status":
                return TaskResult(success=True, data=await self._get_system_status())

            case "check_cost":
                return self._check_cost_policy(kwargs.get("model", "unknown"))

            case "health_check":
                issues = await self._perform_health_check()
                return TaskResult(
                    success=len(issues) == 0,
                    data={"issues": issues, "healthy": len(issues) == 0},
                )

            case "record_cost":
                amount = float(kwargs.get("amount", 0.0))
                model  = kwargs.get("model", "unknown")
                return self._record_cost(amount, model)

            case "alert_history":
                return TaskResult(
                    success=True,
                    data={"alerts": self._alert_history[-20:]},
                )

            case _:
                return TaskResult(success=False, error=f"Unknown action: '{action}'")

    # ═══════════════════════════════════════════════════════════
    #  Cost Policy
    # ═══════════════════════════════════════════════════════════

    def _check_cost_policy(self, model_name: str) -> TaskResult:
        """
        Allowlist-first validation:
          1. If model matches a BLOCKED pattern → deny immediately.
          2. If model matches an ALLOWED pattern → authorize.
          3. Otherwise (unknown) → deny with explicit log.
        """
        model_lower = model_name.lower()

        # Step 1: blocklist has absolute precedence
        for pattern in _BLOCKED_MODEL_PATTERNS:
            if pattern in model_lower:
                msg = (
                    f"🛡️ Cost Violation — Model '{model_name}' matched blocked pattern "
                    f"'{pattern}'. Execution blocked per MOON_CODEX Directive 0.2."
                )
                logger.warning(msg)
                self._fire_alert("cost_violation", msg)
                return TaskResult(success=False, error=msg)

        # Step 2: allowlist
        for pattern in _ALLOWED_MODEL_PATTERNS:
            if pattern in model_lower:
                return TaskResult(success=True, data={"authorized": True, "model": model_name})

        # Step 3: unknown → deny by default
        msg = (
            f"🛡️ Cost Policy — Model '{model_name}' is NOT in the allowlist. "
            f"Denying by default. Add it to _ALLOWED_MODEL_PATTERNS if it is free."
        )
        logger.warning(msg)
        self._fire_alert("unknown_model", msg)
        return TaskResult(success=False, error=msg)

    def _record_cost(self, amount: float, model: str) -> TaskResult:
        """Registers a cost event and alerts if the zero-cost policy is violated."""
        if amount > 0.0:
            self.total_cost_accumulated += amount
            msg = (
                f"💸 Cost recorded: ${amount:.6f} for model '{model}'. "
                f"Total accumulated: ${self.total_cost_accumulated:.6f}. "
                f"MOON_CODEX Directive 0.2 VIOLATION."
            )
            logger.error(msg)
            self._fire_alert("cost_incurred", msg)
            return TaskResult(success=False, error=msg)

        return TaskResult(success=True, data={"cost": 0.0, "accumulated": 0.0})

    # ═══════════════════════════════════════════════════════════
    #  Monitor Loop
    # ═══════════════════════════════════════════════════════════

    async def _monitor_loop(self) -> None:
        """Background loop: health checks + alert publishing."""
        logger.info("Watchdog monitor loop started.")
        while not self._stop_event.is_set():
            try:
                issues = await self._perform_health_check()
                for issue in issues:
                    self._fire_alert("resource", issue)
                    logger.warning(f"WATCHDOG ALERT: {issue}")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Monitor loop error: {exc}")

            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=MONITOR_INTERVAL,
                )
                break  # stop_event was set — exit cleanly
            except asyncio.TimeoutError:
                pass  # normal tick — continue loop

        logger.info("Watchdog monitor loop stopped.")

    # ═══════════════════════════════════════════════════════════
    #  Periodic GitHub Sync
    # ═══════════════════════════════════════════════════════════

    async def _periodic_github_sync(self) -> None:
        """Sync automático com GitHub a cada 30 minutos."""
        logger.info("Watchdog periodic GitHub sync started (30 min interval).")
        while not self._stop_event.is_set():
            try:
                # Aguarda 30 minutos ou até o stop_event ser setado
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._stop_event.wait()),
                        timeout=30 * 60,  # 30 minutos
                    )
                    break  # stop_event foi setado
                except asyncio.TimeoutError:
                    pass  # 30 minutos passaram — executar sync

                from core.services.auto_sync import get_auto_sync
                result = await get_auto_sync().sync_if_dirty(
                    message="chore: periodic auto-sync from watchdog"
                )
                if result.committed:
                    logger.info(f"Watchdog: sync periódico OK — {result.commit_sha}")

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Watchdog: sync periódico falhou: {exc}")

        logger.info("Watchdog periodic GitHub sync stopped.")

    # ═══════════════════════════════════════════════════════════
    #  Health Check
    # ═══════════════════════════════════════════════════════════

    async def _perform_health_check(self) -> List[str]:
        """Returns a list of human-readable issue strings (empty = healthy)."""
        issues: List[str] = []
        status = await self._get_system_status()

        if status["cpu_percent"] > self.max_cpu_percent:
            issues.append(f"High CPU: {status['cpu_percent']:.1f}% (limit {self.max_cpu_percent}%)")

        if status["memory_percent"] > self.max_memory_percent:
            issues.append(f"High RAM: {status['memory_percent']:.1f}% (limit {self.max_memory_percent}%)")

        if status["disk_usage_percent"] > self.max_disk_usage_percent:
            issues.append(f"Low Disk: {status['disk_usage_percent']:.1f}% used (limit {self.max_disk_usage_percent}%)")

        if self.total_cost_accumulated > self.max_daily_cost:
            issues.append(
                f"COST VIOLATION: ${self.total_cost_accumulated:.6f} accumulated "
                f"(max allowed: ${self.max_daily_cost:.2f})"
            )

        return issues

    async def _get_system_status(self) -> Dict[str, Any]:
        """Collects system metrics — psutil preferred, /proc fallback on Linux."""
        try:
            import psutil
            cpu        = psutil.cpu_percent(interval=None)
            mem        = psutil.virtual_memory().percent
            disk       = psutil.disk_usage("/").percent
            proc_count = len(psutil.pids())
        except ImportError:
            cpu        = self._get_cpu_fallback()
            mem        = self._get_mem_fallback()
            disk       = self._get_disk_fallback()
            proc_count = self._get_proc_count_fallback()

        uptime_s = time.monotonic() - self._start_time
        return {
            "cpu_percent":        round(cpu, 2),
            "memory_percent":     round(mem, 2),
            "disk_usage_percent": round(disk, 2),
            "process_count":      proc_count,
            "uptime_seconds":     int(uptime_s),
            "cost_policy":        "Zero Cost (Strict)",
            "accumulated_cost":   round(self.total_cost_accumulated, 8),
            "alert_count":        len(self._alert_history),
        }

    # ═══════════════════════════════════════════════════════════
    #  Alert System (deduplication + MessageBus publish)
    # ═══════════════════════════════════════════════════════════

    def _fire_alert(self, alert_key: str, message: str) -> None:
        """
        Fires an alert with deduplication:
          - Same alert_key will not fire again before ALERT_COOLDOWN seconds.
          - Alert is appended to history and published to MessageBus.
        """
        now  = time.monotonic()
        last = self._alert_last_seen.get(alert_key, 0.0)

        if now - last < ALERT_COOLDOWN:
            return  # still in cooldown — suppress

        self._alert_last_seen[alert_key] = now

        entry = {
            "key":       alert_key,
            "message":   message,
            "timestamp": time.time(),
        }
        self._alert_history.append(entry)

        # Keep history bounded
        if len(self._alert_history) > MAX_ALERT_HISTORY:
            self._alert_history = self._alert_history[-MAX_ALERT_HISTORY:]

        # Publish to MessageBus if available (non-blocking)
        if self._message_bus:
            asyncio.create_task(
                self._message_bus.publish(
                    sender=self.name,
                    topic="watchdog.alert",
                    payload=entry,
                    target="orchestrator",
                ),
                name=f"moon.watchdog.alert.{alert_key}",
            )

    # ═══════════════════════════════════════════════════════════
    #  Metric Fallbacks (/proc — Linux native, zero dependencies)
    # ═══════════════════════════════════════════════════════════

    def _get_cpu_fallback(self) -> float:
        """
        Reads /proc/loadavg and normalises by cpu_count.
        Returns approximate CPU utilisation percentage (0–100).
        """
        try:
            cores    = os.cpu_count() or 1
            with open("/proc/loadavg", "r") as f:
                load_1m = float(f.read().split()[0])
            return min((load_1m / cores) * 100.0, 100.0)
        except Exception:
            return 0.0

    def _get_mem_fallback(self) -> float:
        """Reads /proc/meminfo and computes (used / total) * 100."""
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.read().splitlines()
            info: Dict[str, int] = {}
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
            total     = info.get("MemTotal", 1)
            available = info.get("MemAvailable", total)
            used      = total - available
            return (used / total) * 100.0
        except Exception:
            return 0.0

    def _get_disk_fallback(self) -> float:
        """Uses shutil.disk_usage for root partition percentage."""
        try:
            total, used, _ = shutil.disk_usage("/")
            return (used / total) * 100.0
        except Exception:
            return 0.0

    def _get_proc_count_fallback(self) -> int:
        """Counts numeric entries in /proc (each = one running PID)."""
        try:
            return sum(1 for d in os.listdir("/proc") if d.isdigit())
        except Exception:
            return 0
