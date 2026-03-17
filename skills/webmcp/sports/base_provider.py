"""
WebProviderBase — classe base extensível para qualquer scraper de dados web.

Para criar um novo provider:
    class MeuScraper(WebProviderBase):
        NAME = "meu_scraper"
        BASE_URL = "https://meusite.com"

        async def search_matches(self, query: str) -> SportsQueryResult:
            html = await self._get(f"/busca?q={query}")
            # parse...
            return SportsQueryResult(...)
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from .schemas import SportsQueryResult


class WebProviderBase(ABC):

    NAME: str = "base_provider"
    BASE_URL: str = ""
    TIMEOUT: int = 20
    HEADERS: dict = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_url(self, path: str) -> str:
        return path if path.startswith("http") else self.BASE_URL + path

    async def _get(self, path: str, params: dict = None,
                   extra_headers: dict = None) -> str:
        url = self._build_url(path)
        headers = {**self.HEADERS, **(extra_headers or {})}
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=self.TIMEOUT
        ) as client:
            resp = await client.get(url, params=params or {})
            resp.raise_for_status()
            return resp.text

    async def _get_json(self, path: str, params: dict = None,
                        extra_headers: dict = None) -> dict:
        url = self._build_url(path)
        headers = {**self.HEADERS, "Accept": "application/json",
                   **(extra_headers or {})}
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=self.TIMEOUT
        ) as client:
            resp = await client.get(url, params=params or {})
            resp.raise_for_status()
            return resp.json()

    async def _post_json(self, path: str, payload: dict = None,
                         extra_headers: dict = None) -> dict:
        url = self._build_url(path)
        headers = {**self.HEADERS, "Accept": "application/json",
                   "Content-Type": "application/json", **(extra_headers or {})}
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=self.TIMEOUT
        ) as client:
            resp = await client.post(url, json=payload or {})
            resp.raise_for_status()
            return resp.json()

    @abstractmethod
    async def search_matches(self, query: str) -> SportsQueryResult:
        """Busca partidas por query. Implementação obrigatória."""
        ...

    async def get_lineup(self, match_id: str) -> SportsQueryResult:
        """Busca escalação. Override opcional."""
        return SportsQueryResult(
            query=match_id, provider=self.NAME,
            error=f"{self.NAME}: get_lineup() não implementado",
            success=False,
        )

    def empty_result(self, query: str, error: str = "") -> SportsQueryResult:
        return SportsQueryResult(
            query=query, provider=self.NAME,
            success=not bool(error), error=error,
            scraped_at=self._now_iso(),
        )
