"""
core/scheduler.py
MoonScheduler — asyncio-native autonomous job scheduler.
Zero external dependencies. Reads config from config/radar_schedule.yaml.
Pipeline: RadarAgent -> ReportComposerAgent -> Telegram.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import yaml
from datetime import datetime
from typing import Callable, Awaitable

logger = logging.getLogger("moon.core.scheduler")

SCHEDULE_CONFIG_FILE = "config/radar_schedule.yaml"

_DEFAULT_SCHEDULE: dict = {
    "jobs": [
        {"name": "quick_pulse",      "interval_hours": 6,  "task": "quick_pulse",      "enabled": True},
        {"name": "full_scan",        "interval_hours": 12, "task": "full_scan",         "enabled": True},
        {"name": "strategic_digest", "interval_hours": 24, "task": "strategic_digest",  "enabled": True},
    ],
    "settings": {
        "stagger_seconds": {"quick_pulse": 60, "full_scan": 300, "strategic_digest": 600},
        "log_level": "INFO",
    },
}

TelegramSender = Callable[[str], Awaitable[None]]


class MoonScheduler:
    """
    Lightweight asyncio-based autonomous scheduler for The Moon ecosystem.
    Calls RadarAgent -> ReportComposerAgent -> Telegram on each cycle.
    """

    def __init__(
        self,
        radar_agent,
        report_composer,
        telegram_sender: TelegramSender | None = None,
    ) -> None:
        self.radar_agent = radar_agent
        self.report_composer = report_composer
        self.telegram_sender = telegram_sender
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._config = self._load_config()
        self._job_stats: dict[str, dict] = {}

    def _load_config(self) -> dict:
        if os.path.exists(SCHEDULE_CONFIG_FILE):
            try:
                with open(SCHEDULE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if loaded and "jobs" in loaded:
                        return loaded
            except Exception as e:
                logger.warning(f"[MoonScheduler] Could not load config: {e} — using defaults")
        return _DEFAULT_SCHEDULE

    async def run_pipeline(self, task_name: str) -> bool:
        """Full pipeline: RadarAgent -> ReportComposerAgent -> Telegram."""
        logger.info(f"[MoonScheduler] ▶ Pipeline: {task_name}")
        pipe_start = time.time()

        radar_result = await self.radar_agent.execute(task_name)
        if not radar_result.success:
            logger.error(f"[MoonScheduler] RadarAgent failed: {radar_result.error}")
            return False

        total_new = radar_result.data.get("total_new", 0)
        logger.info(f"[MoonScheduler] Radar: {total_new} new items")

        compose_result = await self.report_composer.execute(
            "compose",
            radar_data=radar_result.data,
            scan_type=task_name,
        )
        if not compose_result.success:
            logger.error(f"[MoonScheduler] ReportComposer failed: {compose_result.error}")
            return False

        report = compose_result.data.get("report", "")
        if report and self.telegram_sender:
            try:
                await self.telegram_sender(report)
                logger.info(
                    f"[MoonScheduler] ✅ Telegram delivered "
                    f"({len(report)} chars, {time.time()-pipe_start:.1f}s)"
                )
            except Exception as e:
                logger.error(f"[MoonScheduler] Telegram failed: {e}")
                return False
        elif not report:
            logger.warning("[MoonScheduler] Empty report — nothing sent")

        self._job_stats[task_name] = {
            "last_run": datetime.utcnow().isoformat(),
            "total_new": total_new,
            "success": True,
        }
        return True

    async def _periodic_job(self, job: dict) -> None:
        """Run a single job at its configured interval indefinitely."""
        interval_seconds = int(job.get("interval_hours", 12)) * 3600
        job_name = job.get("name", "unknown")
        task_name = job.get("task", job_name)
        stagger_map: dict = self._config.get("settings", {}).get("stagger_seconds", {})
        stagger = stagger_map.get(job_name, 0)

        logger.info(f"[MoonScheduler] '{job_name}' starting in {stagger}s, then every {job.get('interval_hours')}h")
        await asyncio.sleep(stagger)

        while self._running:
            cycle_start = time.time()
            try:
                await self.run_pipeline(task_name)
            except Exception as e:
                logger.error(f"[MoonScheduler] Job '{job_name}' error: {e}", exc_info=True)
            elapsed = time.time() - cycle_start
            sleep_time = max(60.0, interval_seconds - elapsed)
            logger.debug(f"[MoonScheduler] '{job_name}' next in {sleep_time:.0f}s")
            await asyncio.sleep(sleep_time)

    def start(self) -> None:
        """Start all enabled jobs as asyncio background tasks."""
        self._running = True
        jobs = self._config.get("jobs", _DEFAULT_SCHEDULE["jobs"])
        enabled = [j for j in jobs if j.get("enabled", True)]
        if not enabled:
            logger.warning("[MoonScheduler] No enabled jobs found")
            return
        for job in enabled:
            task = asyncio.create_task(
                self._periodic_job(job),
                name=f"moon_scheduler_{job['name']}",
            )
            self._tasks.append(task)
        logger.info(f"[MoonScheduler] ✅ {len(enabled)} job(s) started: {[j['name'] for j in enabled]}")

    def stop(self) -> None:
        """Gracefully stop all scheduled jobs."""
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        logger.info("[MoonScheduler] ⏹ Stopped.")

    def get_status(self) -> dict:
        jobs = self._config.get("jobs", [])
        return {
            "running": self._running,
            "active_tasks": len(self._tasks),
            "jobs": [
                {
                    "name": j.get("name"),
                    "interval_hours": j.get("interval_hours"),
                    "enabled": j.get("enabled", True),
                    "last_run": self._job_stats.get(j.get("name", ""), {}).get("last_run", "nunca"),
                }
                for j in jobs
            ],
        }
