"""
WebMCPAgent — Agente de coleta web leve para The Moon Ecosystem.

Modos de operação via task string:
  search:<query>            → DuckDuckGo, retorna lista de resultados
  fetch:<url>               → httpx, extrai conteúdo da página
  search_and_fetch:<query>  → busca + fetch dos 2 primeiros resultados
  deep:<url>                → delega ao BrowserPilot (Playwright) para JS-heavy
  <texto livre>             → tratado como search:<texto>
"""

import time
from typing import Any

from core.agent_base import AgentBase, TaskResult


class WebMCPAgent(AgentBase):

    NAME = "webmcp_agent"

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        start = time.time()
        try:
            result = await self._dispatch(task, **kwargs)
            return TaskResult(
                success=True,
                data=result,
                execution_time=time.time() - start,
            )
        except Exception as exc:
            return TaskResult(
                success=False,
                error=str(exc),
                execution_time=time.time() - start,
            )

    async def _dispatch(self, task: str, **kwargs) -> Any:
        from skills.webmcp.search_engine import search_duckduckgo
        from skills.webmcp.fetcher import fetch_page, needs_browser

        # ── deep: delega ao BrowserPilot via MessageBus ──────────────────
        if task.startswith("deep:"):
            url = task[5:].strip()
            return await self._delegate_to_browser_pilot(url)

        # ── fetch: extração direta ────────────────────────────────────────
        if task.startswith("fetch:"):
            url = task[6:].strip()
            if needs_browser(url):
                return await self._delegate_to_browser_pilot(url)
            page = await fetch_page(url)
            return {
                "mode": "fetch",
                "url": page.url,
                "title": page.title,
                "content": page.content,
                "links": page.links[:10],
                "fetched_at": page.fetched_at,
                "rendered": page.rendered,
            }

        # ── search_and_fetch: busca + fetch ───────────────────────────────
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
                        pages.append({"url": url, "note": "JS-heavy, use deep: para renderizar"})
                    else:
                        page = await fetch_page(url)
                        pages.append({
                            "url": page.url,
                            "title": page.title,
                            "content": page.content[:3000],
                            "rendered": page.rendered,
                        })
                except Exception as e:
                    pages.append({"url": url, "error": str(e)})
            return {"mode": "search_and_fetch", "search": sr.__dict__, "pages": pages}

        # ── search: (ou texto livre) ──────────────────────────────────────
        query = task.replace("search:", "").strip()
        max_r = kwargs.get("max_results", 8)
        sr = await search_duckduckgo(query, max_results=max_r)
        return {"mode": "search", **sr.__dict__}

    async def _delegate_to_browser_pilot(self, url: str) -> dict:
        """
        Delega ao BrowserPilot via MessageBus para páginas JS-heavy.
        Se MessageBus não disponível, retorna instrução clara.
        """
        try:
            from core.message_bus import MessageBus
            bus = MessageBus.get_instance()
            response = await bus.publish(
                sender=self.NAME,
                topic="browser_task",
                payload={"action": "navigate", "url": url},
                target="browser_pilot",
            )
            return {"mode": "deep_via_browser_pilot", "url": url, "response": response}
        except Exception as e:
            return {
                "mode": "deep_unavailable",
                "url": url,
                "note": "BrowserPilot indisponível — use /browser no Telegram",
                "error": str(e),
            }
