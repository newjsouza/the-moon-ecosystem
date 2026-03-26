"""
core/user_profile.py
User Preference Profile — drives all proactive and adaptive behaviors.

Singleton that loads and exposes Johnathan's preferences, goals, and watchlist topics.
All proactive agents (MoonSentinelAgent, ProactiveAgent) read from this profile
to personalize output and respect notification preferences.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("moon.core.user_profile")

PROFILE_PATH = Path("data/user_profile.json")

# ─────────────────────────────────────────────────────────────
#  Singleton
# ─────────────────────────────────────────────────────────────

_profile: Optional["UserProfile"] = None


def get_user_profile() -> "UserProfile":
    """Returns the singleton UserProfile instance."""
    global _profile
    if _profile is None:
        _profile = UserProfile()
    return _profile


# ─────────────────────────────────────────────────────────────
#  UserProfile
# ─────────────────────────────────────────────────────────────

class UserProfile:
    """
    Manages the user's preference profile.

    Usage:
        profile = get_user_profile()
        print(profile.name)                         # "Johnathan"
        print(profile.watchlist_topics)             # list of topics
        print(profile.should_notify_now())          # respects DND
        profile.update({"preferences": {...}})      # persists changes
    """

    def __init__(self, path: Path = PROFILE_PATH) -> None:
        self._path = path
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Loads profile from JSON file."""
        try:
            if self._path.exists():
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"UserProfile loaded from {self._path}")
            else:
                logger.warning(f"UserProfile not found at {self._path} — using defaults")
                self._data = self._defaults()
        except Exception as e:
            logger.error(f"Failed to load UserProfile: {e} — using defaults")
            self._data = self._defaults()

    def _save(self) -> None:
        """Persists profile to JSON file."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._data["last_updated"] = datetime.now().isoformat()
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.info("UserProfile saved.")
        except Exception as e:
            logger.error(f"Failed to save UserProfile: {e}")

    @staticmethod
    def _defaults() -> Dict[str, Any]:
        return {
            "name": "Johnathan",
            "language": "pt-BR",
            "timezone": "America/Sao_Paulo",
            "interests": ["IA autônoma", "automação"],
            "goals": ["The Moon como sócio proativo"],
            "preferences": {
                "preferred_briefing_hour": 8,
                "preferred_evening_report_hour": 20,
                "approve_before_deploy": True,
                "approve_before_skill_integration": True,
                "notify_on_trend": True,
                "notify_on_new_skill_discovered": True,
                "notify_on_health_issue": True,
            },
            "watchlist_topics": ["agentic AI", "LLM open source"],
            "do_not_disturb": {"enabled": False, "start_hour": 23, "end_hour": 7},
        }

    # ──────────────────────────────────────────────────────────
    #  Properties
    # ──────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._data.get("name", "Johnathan")

    @property
    def language(self) -> str:
        return self._data.get("language", "pt-BR")

    @property
    def interests(self) -> List[str]:
        return self._data.get("interests", [])

    @property
    def goals(self) -> List[str]:
        return self._data.get("goals", [])

    @property
    def watchlist_topics(self) -> List[str]:
        return self._data.get("watchlist_topics", [])

    @property
    def preferred_briefing_hour(self) -> int:
        return self._data.get("preferences", {}).get("preferred_briefing_hour", 8)

    @property
    def preferred_evening_report_hour(self) -> int:
        return self._data.get("preferences", {}).get("preferred_evening_report_hour", 20)

    @property
    def approve_before_deploy(self) -> bool:
        return self._data.get("preferences", {}).get("approve_before_deploy", True)

    @property
    def approve_before_skill_integration(self) -> bool:
        return self._data.get("preferences", {}).get("approve_before_skill_integration", True)

    @property
    def notify_on_trend(self) -> bool:
        return self._data.get("preferences", {}).get("notify_on_trend", True)

    @property
    def notify_on_new_skill(self) -> bool:
        return self._data.get("preferences", {}).get("notify_on_new_skill_discovered", True)

    @property
    def notify_on_health_issue(self) -> bool:
        return self._data.get("preferences", {}).get("notify_on_health_issue", True)

    # ──────────────────────────────────────────────────────────
    #  DND Logic
    # ──────────────────────────────────────────────────────────

    def should_notify_now(self) -> bool:
        """Returns True if current time is outside Do-Not-Disturb window."""
        dnd = self._data.get("do_not_disturb", {})
        if not dnd.get("enabled", False):
            return True
        hour = datetime.now().hour
        start = dnd.get("start_hour", 23)
        end = dnd.get("end_hour", 7)
        if start > end:  # Crosses midnight
            return not (hour >= start or hour < end)
        return not (start <= hour < end)

    # ──────────────────────────────────────────────────────────
    #  Update
    # ──────────────────────────────────────────────────────────

    def update(self, changes: Dict[str, Any]) -> None:
        """
        Deep-merges changes into profile and persists.

        Example:
            profile.update({"preferences": {"notify_on_trend": False}})
        """
        self._deep_merge(self._data, changes)
        self._save()

    @staticmethod
    def _deep_merge(base: dict, overlay: dict) -> None:
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                UserProfile._deep_merge(base[key], value)
            else:
                base[key] = value

    # ──────────────────────────────────────────────────────────
    #  Greeting helper
    # ──────────────────────────────────────────────────────────

    def greeting(self) -> str:
        """Returns time-appropriate greeting in user's language."""
        hour = datetime.now().hour
        if hour < 12:
            return f"Bom dia, {self.name} ☀️"
        elif hour < 18:
            return f"Boa tarde, {self.name} 🌤️"
        else:
            return f"Boa noite, {self.name} 🌙"

    def __repr__(self) -> str:
        return f"UserProfile(name={self.name!r}, topics={len(self.watchlist_topics)})"
