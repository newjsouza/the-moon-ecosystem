"""
SofaScoreScraper — consome endpoints JSON públicos do SofaScore.
Esses endpoints são os mesmos usados pelo app/site oficial.
Não requer autenticação para dados básicos. Custo: Zero.
"""
from datetime import datetime, timezone
from typing import List, Optional

from .base_provider import WebProviderBase
from .schemas import MatchInfo, Lineup, LineupPlayer, SportsQueryResult


class SofaScoreScraper(WebProviderBase):

    NAME = "sofascore"
    BASE_URL = "https://api.sofascore.com/api/v1"
    HEADERS = {
        **WebProviderBase.HEADERS,
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
    }

    # ── Busca ──────────────────────────────────────────────────

    async def search_matches(self, query: str) -> SportsQueryResult:
        try:
            data = await self._get_json(
                "/search/all", params={"q": query, "page": "0"}
            )
            events = data.get("events", {}).get("results", [])
            matches = [
                m for m in (self._parse_event(ev) for ev in events[:15])
                if m is not None
            ]
            return SportsQueryResult(
                query=query, provider=self.NAME,
                matches=matches, scraped_at=self._now_iso(),
            )
        except Exception as e:
            return self.empty_result(query, error=str(e))

    async def get_today_matches(self, sport: str = "football") -> SportsQueryResult:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            data = await self._get_json(
                f"/sport/{sport}/scheduled-events/{today}"
            )
            matches = [
                m for m in (self._parse_event(ev)
                            for ev in data.get("events", []))
                if m is not None
            ]
            return SportsQueryResult(
                query=f"today_{sport}", provider=self.NAME,
                matches=matches, scraped_at=self._now_iso(),
            )
        except Exception as e:
            return self.empty_result(f"today_{sport}", error=str(e))

    async def get_match_by_teams(
        self, home: str, away: str, date_str: str = ""
    ) -> SportsQueryResult:
        result = await self.search_matches(f"{home} {away}")
        if date_str and result.matches:
            result.matches = [
                m for m in result.matches
                if date_str in (m.kickoff_utc or "")
            ]
        return result

    # ── Escalações ────────────────────────────────────────────

    async def get_lineup(self, match_id: str) -> SportsQueryResult:
        try:
            data = await self._get_json(f"/event/{match_id}/lineups")
            home = self._parse_lineup(data.get("home", {}))
            away = self._parse_lineup(data.get("away", {}))
            match = MatchInfo(
                match_id=match_id,
                home_team=home.team_name if home else "",
                away_team=away.team_name if away else "",
                home_lineup=home,
                away_lineup=away,
                source=self.NAME,
                scraped_at=self._now_iso(),
            )
            return SportsQueryResult(
                query=match_id, provider=self.NAME,
                matches=[match], scraped_at=self._now_iso(),
            )
        except Exception as e:
            return self.empty_result(match_id, error=str(e))

    # ── Parsers ───────────────────────────────────────────────

    def _parse_event(self, ev: dict) -> Optional[MatchInfo]:
        try:
            start_ts = ev.get("startTimestamp")
            kickoff = (
                datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()
                if start_ts else None
            )
            return MatchInfo(
                match_id=str(ev.get("id", "")),
                home_team=ev.get("homeTeam", {}).get("name", ""),
                away_team=ev.get("awayTeam", {}).get("name", ""),
                competition=ev.get("tournament", {}).get("name", ""),
                kickoff_utc=kickoff,
                status=ev.get("status", {}).get("type", "scheduled"),
                score_home=ev.get("homeScore", {}).get("current"),
                score_away=ev.get("awayScore", {}).get("current"),
                source=self.NAME,
                scraped_at=self._now_iso(),
            )
        except Exception:
            return None

    def _parse_lineup(self, data: dict) -> Optional[Lineup]:
        if not data:
            return None
        players = []
        for p in data.get("players", []):
            info = p.get("player", {})
            players.append(LineupPlayer(
                name=info.get("name", ""),
                position=p.get("position", ""),
                number=info.get("jerseyNumber", 0),
                is_starter=not p.get("substitute", True),
                is_captain=p.get("captain", False),
            ))
        return Lineup(
            team_name=data.get("teamColors", {}).get("text", ""),
            players=players,
            formation=data.get("formation", ""),
            confirmed=True,
            source=self.NAME,
            scraped_at=self._now_iso(),
        )
