"""
agents/radar_agent.py
Proactive intelligence radar for The Moon ecosystem.
Orchestrates 5 scanners: GitHub, HuggingFace, RSS, LLM Releases, PyPI.
Deduplication via MD5 hash ring buffer (1000 entries) in data/radar_state.json.
Supported tasks: 'quick_pulse' | 'full_scan' | 'strategic_digest'
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

from core.agent_base import AgentBase, AgentPriority, TaskResult
from skills.radar import RadarItem
from skills.radar.github_trending import scan_github_trending
from skills.radar.huggingface_scanner import scan_huggingface_models, scan_huggingface_spaces
from skills.radar.rss_scanner import scan_rss_feeds
from skills.radar.llm_releases_scanner import scan_openrouter_free_models, scan_groq_models
from skills.radar.pypi_scanner import scan_pypi_new_packages

logger = logging.getLogger("moon.agents.radar")

STATE_FILE = "data/radar_state.json"
MAX_SEEN_HASHES = 1000


class RadarAgent(AgentBase):
    """
    Proactive intelligence radar for The Moon ecosystem.
    Follows the exact same AgentBase contract as WatchdogAgent.
    """

    def __init__(self, message_bus=None, llm=None) -> None:
        super().__init__()
        self.name = "RadarAgent"
        self.description = "Proactive tech intelligence: GitHub, HuggingFace, RSS, LLM, PyPI."
        self.priority = AgentPriority.MEDIUM
        self._message_bus = message_bus
        self._llm = llm
        os.makedirs("data", exist_ok=True)
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load radar state: {e}")
        return {"seen_hashes": [], "last_scans": {}}

    def _save_state(self) -> None:
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save radar state: {e}")

    def _is_seen(self, item_hash: str) -> bool:
        return item_hash in self._state.get("seen_hashes", [])

    def _mark_seen(self, items: list[RadarItem]) -> None:
        seen: list[str] = self._state.setdefault("seen_hashes", [])
        for item in items:
            if item.item_hash not in seen:
                seen.append(item.item_hash)
        self._state["seen_hashes"] = seen[-MAX_SEEN_HASHES:]
        self._save_state()

    def _filter_new(self, items: list[RadarItem]) -> list[RadarItem]:
        return [item for item in items if not self._is_seen(item.item_hash)]

    def _serialize_items(self, items: list[RadarItem]) -> list[dict]:
        return [
            {
                "source": i.source,
                "title": i.title,
                "description": i.description,
                "url": i.url,
                "category": i.category,
                "item_hash": i.item_hash,
                "timestamp": i.timestamp,
            }
            for i in items
        ]

    def get_status(self) -> dict:
        return {
            "seen_hashes_count": len(self._state.get("seen_hashes", [])),
            "last_scans": self._state.get("last_scans", {}),
            "state_file": STATE_FILE,
        }

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        task: 'quick_pulse' | 'full_scan' | 'strategic_digest'
        kwargs:
            sources (list[str]): restrict to specific scanner keys
            force_all (bool): skip deduplication
        """
        start = time.time()
        task_type = task.strip().lower() if task.strip() else "full_scan"
        force_all: bool = kwargs.get("force_all", False)
        sources: list[str] | None = kwargs.get("sources", None)

        try:
            all_items: list[RadarItem] = []

            if sources is None or "github_trending" in sources:
                all_items.extend(await scan_github_trending())

            if sources is None or "huggingface" in sources:
                all_items.extend(await scan_huggingface_models())
                all_items.extend(await scan_huggingface_spaces())

            if task_type in ("full_scan", "strategic_digest"):
                if sources is None or "rss" in sources:
                    all_items.extend(await scan_rss_feeds())
                if sources is None or "llm_releases" in sources:
                    all_items.extend(await scan_openrouter_free_models())
                    all_items.extend(await scan_groq_models())
                if sources is None or "pypi" in sources:
                    all_items.extend(await scan_pypi_new_packages())

            new_items = all_items if force_all else self._filter_new(all_items)
            self._mark_seen(new_items)

            self._state.setdefault("last_scans", {})[task_type] = datetime.utcnow().isoformat()
            self._save_state()

            exec_time = time.time() - start
            logger.info(
                f"[RadarAgent] {task_type}: {len(new_items)} new / "
                f"{len(all_items)} scanned in {exec_time:.2f}s"
            )

            return TaskResult(
                success=True,
                data={
                    "scan_type": task_type,
                    "new_items": self._serialize_items(new_items),
                    "total_scanned": len(all_items),
                    "total_new": len(new_items),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                execution_time=exec_time,
            )

        except Exception as e:
            logger.error(f"[RadarAgent] _execute error: {e}", exc_info=True)
            return TaskResult(success=False, error=str(e), execution_time=time.time() - start)
