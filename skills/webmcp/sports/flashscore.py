"""
FlashscoreScraper — HTML scraping do Flashscore Brasil.
Backup para SofaScore. Especializado em partidas ao vivo.
Custo: Zero.
"""
import re
from datetime import datetime, timezone
from typing import List

from .base_provider import WebProviderBase
from .schemas import MatchInfo, SportsQueryResult

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False


class FlashscoreScraper(WebProviderBase):

    NAME = "flashscore"
    BASE_URL = "https://www.flashscore.com.br"
    HEADERS = {
        **WebProviderBase.HEADERS,
        "X-Fsign": "SW9D1eZo",
    }

    async def search_matches(self, query: str) -> SportsQueryResult:
        try:
            html = await self._get("/search/", params={"q": query})
            return SportsQueryResult(
                query=query, provider=self.NAME,
                matches=self._parse_matches(html),
                scraped_at=self._now_iso(),
            )
        except Exception as e:
            return self.empty_result(query, error=str(e))

    async def get_live_matches(self) -> SportsQueryResult:
        try:
            html = await self._get("/futebol/")
            return SportsQueryResult(
                query="live", provider=self.NAME,
                matches=self._parse_live(html),
                scraped_at=self._now_iso(),
            )
        except Exception as e:
            return self.empty_result("live", error=str(e))

    def _parse_matches(self, html: str) -> List[MatchInfo]:
        matches = []
        if not _BS4:
            return matches
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select("[class*='event__match']")[:20]:
            home = el.select_one("[class*='home']")
            away = el.select_one("[class*='away']")
            if home and away:
                matches.append(MatchInfo(
                    match_id=el.get("id", ""),
                    home_team=home.get_text(strip=True),
                    away_team=away.get_text(strip=True),
                    source=self.NAME,
                    scraped_at=self._now_iso(),
                ))
        return matches

    def _parse_live(self, html: str) -> List[MatchInfo]:
        matches = []
        if not _BS4:
            return matches
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("[data-id]")[:30]:
            texts = [t.strip() for t in row.get_text("|").split("|") if t.strip()]
            if len(texts) >= 2:
                matches.append(MatchInfo(
                    match_id=row.get("data-id", ""),
                    home_team=texts[0],
                    away_team=texts[1],
                    status="live",
                    source=self.NAME,
                    scraped_at=self._now_iso(),
                ))
        return matches
