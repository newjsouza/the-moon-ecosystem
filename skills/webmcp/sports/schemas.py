from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


@dataclass
class LineupPlayer:
    name: str
    position: str = ""
    number: int = 0
    is_starter: bool = True
    is_captain: bool = False


@dataclass
class Lineup:
    team_name: str
    players: List[LineupPlayer] = field(default_factory=list)
    formation: str = ""
    confirmed: bool = False
    source: str = ""
    scraped_at: str = ""

    @property
    def starters(self) -> List[LineupPlayer]:
        return [p for p in self.players if p.is_starter]

    @property
    def bench(self) -> List[LineupPlayer]:
        return [p for p in self.players if not p.is_starter]


@dataclass
class MatchInfo:
    match_id: str
    home_team: str
    away_team: str
    competition: str = ""
    kickoff_utc: Optional[str] = None
    status: str = "scheduled"
    score_home: Optional[int] = None
    score_away: Optional[int] = None
    venue: str = ""
    home_lineup: Optional[Lineup] = None
    away_lineup: Optional[Lineup] = None
    odds: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    scraped_at: str = ""

    @property
    def minutes_to_kickoff(self) -> Optional[float]:
        if not self.kickoff_utc:
            return None
        try:
            ko = datetime.fromisoformat(self.kickoff_utc)
            if ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return (ko - now).total_seconds() / 60
        except Exception:
            return None

    @property
    def lineup_window_active(self) -> bool:
        """True se estamos entre t-70min e t-10min (janela de divulgação)."""
        mins = self.minutes_to_kickoff
        if mins is None:
            return False
        return 10 <= mins <= 70


@dataclass
class NewsArticle:
    title: str
    url: str
    source: str
    summary: str = ""
    published_at: str = ""
    mentions_lineup: bool = False
    teams_mentioned: List[str] = field(default_factory=list)


@dataclass
class SportsQueryResult:
    query: str
    provider: str
    matches: List[MatchInfo] = field(default_factory=list)
    news: List[NewsArticle] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""
    scraped_at: str = ""
