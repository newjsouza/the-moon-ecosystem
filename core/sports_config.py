"""
SportsConfig — competition IDs and report templates for The Moon sports coverage.
Uses football-data.org API v4 (FOOTBALL_DATA_API_KEY in env).
Extend competition_ids as needed for new leagues.
"""
from dataclasses import dataclass, field
from typing import Optional


# ── Competition IDs (football-data.org v4) ────────────────────
COMPETITION_IDS = {
    # Brazilian
    "brasileirao":       "BSA",
    "brasileirao_b":     "BSB",
    "copa_brasil":       "BBC",

    # European top 5
    "premier_league":    "PL",
    "la_liga":           "PD",
    "bundesliga":        "BL1",
    "serie_a_ita":       "SA",
    "ligue_1":           "FL1",

    # International
    "champions_league":  "CL",
    "europa_league":     "EL",
    "world_cup":         "WC",
    "copa_america":      "CLI",
}

# ── Default competitions to monitor ───────────────────────────
DEFAULT_COMPETITIONS = ["brasileirao", "champions_league", "premier_league"]


@dataclass
class ReportConfig:
    """Configuration for a sports report run."""
    competition: str = "brasileirao"
    competition_id: str = "BSA"
    report_type: str = "weekly"         # weekly | matchday | standings | scorers
    publish_blog: bool = True
    notify_telegram: bool = True
    language: str = "pt-BR"
    dry_run: bool = False
    max_matches: int = 10
    include_standings: bool = True
    include_scorers: bool = True
    include_analysis: bool = True       # LLM narrative analysis

    @classmethod
    def for_competition(cls, competition_name: str, **kwargs) -> "ReportConfig":
        comp_id = COMPETITION_IDS.get(competition_name, competition_name.upper())
        return cls(competition=competition_name,
                   competition_id=comp_id, **kwargs)