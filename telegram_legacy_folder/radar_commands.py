"""
telegram/radar_commands.py
Radar command handlers for The Moon Telegram bot.

Commands:
  !radar now     — full_scan imediato
  !radar pulse   — quick_pulse imediato
  !radar digest  — strategic_digest imediato
  !radar status  — status do scheduler + estado do radar
"""
from __future__ import annotations
import logging
from typing import Callable, Awaitable

logger = logging.getLogger("moon.telegram.radar_commands")

_TASK_MAP: dict[str, str] = {
    "now":    "full_scan",
    "pulse":  "quick_pulse",
    "digest": "strategic_digest",
}


async def handle_radar_command(
    text: str,
    radar_agent,
    report_composer,
    scheduler,
    send_message: Callable[[str], Awaitable[None]],
) -> bool:
    """
    Parse and execute a !radar command.
    Returns True if handled, False otherwise.
    """
    text_clean = text.strip().lower()
    if not text_clean.startswith("!radar"):
        return False

    parts = text_clean.split()
    subcommand = parts[1] if len(parts) > 1 else "now"

    if subcommand == "status":
        await _handle_status(radar_agent, scheduler, send_message)
        return True

    task_name = _TASK_MAP.get(subcommand, "full_scan")
    await _handle_scan(task_name, radar_agent, report_composer, send_message)
    return True


async def _handle_scan(
    task_name: str,
    radar_agent,
    report_composer,
    send_message: Callable[[str], Awaitable[None]],
) -> None:
    """Execute pipeline and deliver report via Telegram."""
    await send_message(f"🔭 Iniciando radar: *{task_name}*...\n_Aguarde alguns instantes._")
    try:
        radar_result = await radar_agent.execute(task_name)
        if not radar_result.success:
            await send_message(f"❌ Radar falhou: `{radar_result.error}`")
            return

        compose_result = await report_composer.execute(
            "compose",
            radar_data=radar_result.data,
            scan_type=task_name,
        )
        if not compose_result.success:
            await send_message(f"❌ Erro ao compor relatório: `{compose_result.error}`")
            return

        report = compose_result.data.get("report", "")
        await send_message(report if report else "⚠️ Relatório vazio gerado.")

    except Exception as e:
        logger.error(f"[RadarCommand] Scan error: {e}", exc_info=True)
        await send_message(f"❌ Erro inesperado: `{e}`")


async def _handle_status(
    radar_agent,
    scheduler,
    send_message: Callable[[str], Awaitable[None]],
) -> None:
    """Send radar + scheduler status to Telegram."""
    try:
        radar_status = radar_agent.get_status()
        sched_status = scheduler.get_status() if scheduler else {}

        lines = ["🌙 *The Moon — Radar Status*\n"]
        lines.append(f"📦 Hashes armazenados: `{radar_status.get('seen_hashes_count', 0)}`")

        last_scans = radar_status.get("last_scans", {})
        if last_scans:
            lines.append("\n🕐 *Últimos scans:*")
            for scan_type, ts in last_scans.items():
                lines.append(f"  • {scan_type}: _{ts[:19]}_")

        if sched_status:
            running_icon = "✅ rodando" if sched_status.get("running") else "⏹ parado"
            lines.append(f"\n⚙️ *Scheduler:* {running_icon}")
            for job in sched_status.get("jobs", []):
                status_icon = "✅" if job.get("enabled") else "⏸"
                lines.append(
                    f"  {status_icon} `{job['name']}` — a cada {job['interval_hours']}h "
                    f"| último: _{job.get('last_run', 'nunca')}_"
                )

        await send_message("\n".join(lines))

    except Exception as e:
        logger.error(f"[RadarCommand] Status error: {e}", exc_info=True)
        await send_message(f"❌ Erro ao obter status: `{e}`")
