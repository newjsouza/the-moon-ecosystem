"""
WebMCPAgent — Coleta web inteligente para The Moon Ecosystem.

Modos de operação (task string):
  sports:<sub>                     → dados esportivos (SofaScore, Flashscore, news)
  sports:lineup:<home> vs <away>   → escalações multi-fonte
  sports:live                      → partidas ao vivo agora
  sports:today                     → partidas de hoje
  sports:news:<topic>              → notícias esportivas
  sports:match:<query>             → buscar partida
  search:<query>                   → DuckDuckGo (sem API)
  fetch:<url>                      → httpx leve; delega JS-heavy ao BrowserPilot
  search_and_fetch:<query>         → busca + fetch dos top resultados
  deep:<url>                       → BrowserPilot (Playwright)
  <texto livre>                    → auto-detect: sports ou search
"""
import time
from typing import Any

from core.agent_base import AgentBase, TaskResult


class WebMCPAgent(AgentBase):

    NAME = "webmcp_agent"

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        start = time.time()
        try:
            data = await self._dispatch(task.strip(), **kwargs)
            return TaskResult(
                success=True, data=data,
                execution_time=time.time() - start,
            )
        except Exception as exc:
            return TaskResult(
                success=False, error=str(exc),
                execution_time=time.time() - start,
            )

    async def _dispatch(self, task: str, **kwargs) -> Any:
        from skills.webmcp.router import route, _is_sports
        from skills.webmcp.search_engine import search_duckduckgo
        from skills.webmcp.fetcher import fetch_page, needs_browser

        # ── sports ou auto-detect ──────────────────────────────
        if task.startswith("sports:") or _is_sports(task):
            routed = await route(task, **kwargs)
            if "__delegate__" not in routed:
                return routed
            task = routed["__delegate__"]

        # ── deep: BrowserPilot ─────────────────────────────────
        if task.startswith("deep:"):
            return await self._delegate_browser(task[5:].strip())

        # ── fetch: ─────────────────────────────────────────────
        if task.startswith("fetch:"):
            url = task[6:].strip()
            if needs_browser(url):
                return await self._delegate_browser(url)
            page = await fetch_page(url)
            return {
                "mode": "fetch", "url": page.url, "title": page.title,
                "content": page.content, "links": page.links[:10],
                "fetched_at": page.fetched_at,
            }

        # ── search_and_fetch: ──────────────────────────────────
        if task.startswith("search_and_fetch:"):
            query = task[17:].strip()
            sr = await search_duckduckgo(query, max_results=5)
            pages = []
            for item in sr.results[:2]:
                url = item.get("url", "")
                if not url:
                    continue
                try:
                    if needs_browser(url):
                        pages.append({"url": url, "note": "JS-heavy, use deep:"})
                    else:
                        p = await fetch_page(url)
                        pages.append({
                            "url": p.url, "title": p.title,
                            "content": p.content[:3000],
                        })
                except Exception as e:
                    pages.append({"url": url, "error": str(e)})
            return {"mode": "search_and_fetch", "search": sr.__dict__, "pages": pages}

        # ── search: (padrão) ───────────────────────────────────
        query = task.replace("search:", "").strip()
        sr = await search_duckduckgo(query, max_results=kwargs.get("max_results", 8))
        return {"mode": "search", **sr.__dict__}

    async def _delegate_browser(self, url: str) -> dict:
        try:
            from core.message_bus import MessageBus
            bus = MessageBus.get_instance()
            resp = await bus.publish(
                sender=self.NAME,
                topic="browser_task",
                payload={"action": "navigate", "url": url},
                target="browser_pilot",
            )
            return {"mode": "deep_via_browser_pilot", "url": url, "response": resp}
        except Exception as e:
            return {
                "mode": "deep_unavailable", "url": url,
                "note": "BrowserPilot indisponível — use /browser no Telegram",
                "error": str(e),
            }
