"""
LineupDetector — orquestra coleta de escalações de múltiplas fontes.

Estratégia em cascata (para de buscar ao primeiro sucesso):
  1. SofaScore via match_id  (API JSON — mais confiável)
  2. SofaScore via busca por times
  3. Sites de notícias esportivas (GloboEsporte, ESPN, etc.)

Ideal para polling automático no APEX Betting: t-70min até t-5min.
"""
from datetime import datetime, timezone
from typing import Optional

from .schemas import SportsQueryResult
from .sofascore import SofaScoreScraper
from .flashscore import FlashscoreScraper
from .news import SportsNewsScraper


class LineupDetector:

    def __init__(self):
        self._sofascore = SofaScoreScraper()
        self._flashscore = FlashscoreScraper()
        self._news = SportsNewsScraper()

    async def detect_lineups(
        self,
        home_team: str,
        away_team: str,
        match_id: Optional[str] = None,
        competition: str = "",
    ) -> SportsQueryResult:
        """Tenta todas as fontes em cascata. Retorna a primeira com sucesso."""
        query = f"{home_team} vs {away_team}"

        # Tentativa 1: SofaScore direto por match_id
        if match_id:
            r = await self._sofascore.get_lineup(match_id)
            if r.success and r.matches and (
                r.matches[0].home_lineup or r.matches[0].away_lineup
            ):
                r.raw_data["lineup_source"] = "sofascore_api_direct"
                return r

        # Tentativa 2: Buscar match_id via search, depois pegar lineup
        ss = await self._sofascore.get_match_by_teams(home_team, away_team)
        if ss.success and ss.matches:
            mid = ss.matches[0].match_id
            if mid:
                r = await self._sofascore.get_lineup(mid)
                if r.success and r.matches and (
                    r.matches[0].home_lineup or r.matches[0].away_lineup
                ):
                    r.raw_data["lineup_source"] = "sofascore_api_search"
                    return r

        # Tentativa 3: Notícias esportivas
        r = await self._news.search_lineup_news(home_team, away_team, competition)
        if r.news:
            r.raw_data["lineup_source"] = "news_sites"
            return r

        return SportsQueryResult(
            query=query, provider="lineup_detector",
            success=False,
            error=(
                f"Escalação indisponível para {home_team} vs {away_team}. "
                "Pode não ter sido divulgada ainda."
            ),
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )

    async def poll_lineup_status(
        self,
        home_team: str,
        away_team: str,
        match_id: Optional[str] = None,
    ) -> dict:
        """
        Retorna dict de status — ideal para polling automático no APEX.
        Chamar a cada 5 minutos entre t-70min e kickoff.
        """
        r = await self.detect_lineups(home_team, away_team, match_id)
        home_ok = False
        away_ok = False

        if r.matches:
            m = r.matches[0]
            home_ok = bool(m.home_lineup and m.home_lineup.confirmed)
            away_ok = bool(m.away_lineup and m.away_lineup.confirmed)

        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_confirmed": home_ok,
            "away_confirmed": away_ok,
            "both_confirmed": home_ok and away_ok,
            "news_found": len(r.news),
            "lineup_news": sum(1 for n in r.news if n.mentions_lineup),
            "source": r.raw_data.get("lineup_source", "none"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
