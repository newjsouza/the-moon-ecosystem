"""
SportsNewsScraper — coleta notícias esportivas de múltiplos portais.

Portais monitorados (sem API):
  GloboEsporte (ge.globo.com), UOL Esportes, ESPN Brasil,
  Lance!, Goal Brasil, Superesportes, Torcedores, Terra Esportes

Prioridade especial: artigos confirmando escalação (t-50min).
Custo: Zero — DuckDuckGo HTML + httpx.
"""
from datetime import datetime, timezone
from typing import List, Dict

from ..search_engine import search_duckduckgo
from ..fetcher import fetch_page
from .schemas import NewsArticle, SportsQueryResult


LINEUP_KEYWORDS = [
    "escalação", "time confirmado", "onze inicial", "11 inicial",
    "provável escalação", "confirmada", "deve escalar",
    "starting xi", "lineups", "titulares",
]

NEWS_SOURCES: Dict[str, str] = {
    "ge.globo.com": "GloboEsporte",
    "esporte.uol.com.br": "UOL Esportes",
    "espn.com.br": "ESPN Brasil",
    "lance.com.br": "Lance!",
    "goal.com/pt-br": "Goal Brasil",
    "superesportes.com.br": "Superesportes",
    "torcedores.com": "Torcedores",
    "terra.com.br/esportes": "Terra Esportes",
    "uol.com.br/esporte": "UOL Esporte",
    "ogol.com.br": "OGol",
}

_PRIORITY_SITES = list(NEWS_SOURCES.keys())[:5]


def is_lineup_news(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in LINEUP_KEYWORDS)


def detect_teams(text: str, team_hints: List[str]) -> List[str]:
    return [t for t in team_hints if t.lower() in text.lower()]


def detect_source(url: str) -> str:
    for domain, name in NEWS_SOURCES.items():
        if domain in url:
            return name
    return "Esportes"


class SportsNewsScraper:

    NAME = "sports_news"

    async def search_lineup_news(
        self, home: str, away: str, extra: str = ""
    ) -> SportsQueryResult:
        """Escalações para uma partida específica. Usar t-70min até t-10min."""
        query = f"escalação {home} {away} {extra}".strip()
        return await self._search(query, team_hints=[home, away])

    async def search_team_news(
        self, team: str, competition: str = ""
    ) -> SportsQueryResult:
        query = f"{team} escalação {competition}".strip()
        return await self._search(query, team_hints=[team])

    async def get_latest_sports_news(self, topic: str = "futebol") -> SportsQueryResult:
        return await self._search(f"{topic} hoje", team_hints=[])

    async def fetch_article_full(self, url: str) -> str:
        try:
            page = await fetch_page(url)
            return page.content
        except Exception as e:
            return f"Erro: {e}"

    async def _search(
        self, query: str, team_hints: List[str]
    ) -> SportsQueryResult:
        articles: List[NewsArticle] = []
        try:
            site_filter = " OR ".join(f"site:{s}" for s in _PRIORITY_SITES)
            sr = await search_duckduckgo(
                f"{query} ({site_filter})", max_results=12
            )
            for item in sr.results:
                url = item.get("url", "")
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                articles.append(NewsArticle(
                    title=title,
                    url=url,
                    source=detect_source(url),
                    summary=snippet,
                    mentions_lineup=is_lineup_news(title, snippet),
                    teams_mentioned=detect_teams(title + " " + snippet, team_hints),
                ))
            # escalação first
            articles.sort(key=lambda a: (not a.mentions_lineup, a.source))
        except Exception as e:
            return SportsQueryResult(
                query=query, provider=self.NAME,
                success=False, error=str(e),
            )
        return SportsQueryResult(
            query=query, provider=self.NAME, news=articles,
            raw_data={"lineup_articles": sum(1 for a in articles if a.mentions_lineup)},
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )
