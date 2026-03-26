"""
agents/deep_web_research_agent.py
DeepWebResearchAgent — Abelha Coletora da Colmeia.
Pesquisa profunda e autônoma em GitHub, HuggingFace e Arxiv.
Sintetiza resultados via LLMRouter (Groq, zero custo).
Armazena descobertas no MemoryAgent via MessageBus.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import arxiv
import requests
from huggingface_hub import HfApi

from core.agent_base import AgentBase, TaskResult
from core.message_bus import MessageBus
from agents.llm import LLMRouter

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_DEFAULT_SOURCES = ["github", "huggingface", "arxiv"]


class DeepWebResearchAgent(AgentBase):
    """
    Abelha Coletora da Colmeia.
    Pesquisa profunda e autônoma em GitHub, HuggingFace e Arxiv.
    Sintetiza resultados via LLMRouter (Groq, zero custo).
    Armazena descobertas no MemoryAgent via MessageBus.
    Responde a research.request e publica em research.result.
    """

    def __init__(self, bus: MessageBus, llm: LLMRouter):
        super().__init__()
        self.name = "DeepWebResearchAgent"
        self.description = "Pesquisa profunda em GitHub, HuggingFace e Arxiv"
        self._bus = bus
        self._llm = llm
        self._github_token: str = os.environ.get("GITHUB_TOKEN", "")
        self._hf_api = HfApi()
        self._arxiv_client = arxiv.Client()
        self._github_headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._github_token:
            self._github_headers["Authorization"] = f"Bearer {self._github_token}"

    async def start(self) -> None:
        """Inicia o agente e subscreve ao tópico research.request."""
        self._bus.subscribe("research.request", self._on_research_request_wrapper)
        asyncio.create_task(self._heartbeat_loop())
        logger.info("DeepWebResearchAgent iniciado — fontes: %s", _DEFAULT_SOURCES)

    # ─────────────────────────────────────────────
    # FONTES DE PESQUISA
    # ─────────────────────────────────────────────

    async def _search_github(
        self, query: str, max_results: int = 10, sort: str = "stars"
    ) -> list[dict]:
        """Busca repositórios no GitHub."""
        loop = asyncio.get_event_loop()
        params = {
            "q": query,
            "sort": sort,
            "order": "desc",
            "per_page": min(max_results, 30),
        }
        try:
            resp = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    f"{_GITHUB_API}/search/repositories",
                    headers=self._github_headers,
                    params=params,
                    timeout=15,
                ),
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            return [
                {
                    "source": "github",
                    "title": r["full_name"],
                    "url": r["html_url"],
                    "description": r.get("description", "") or "",
                    "stars": r.get("stargazers_count", 0),
                    "language": r.get("language", ""),
                    "topics": r.get("topics", []),
                    "updated_at": r.get("updated_at", ""),
                }
                for r in items
            ]
        except Exception as e:
            logger.warning("GitHub search falhou: %s", e)
            return []

    async def _search_huggingface(
        self, query: str, max_results: int = 10
    ) -> list[dict]:
        """Busca modelos no HuggingFace Hub."""
        loop = asyncio.get_event_loop()
        try:
            models = await loop.run_in_executor(
                None,
                lambda: list(
                    self._hf_api.list_models(
                        search=query,
                        limit=max_results,
                        sort="downloads",
                        direction=-1,
                    )
                ),
            )
            return [
                {
                    "source": "huggingface",
                    "title": m.modelId,
                    "url": f"https://huggingface.co/{m.modelId}",
                    "description": getattr(m, "pipeline_tag", "") or "",
                    "downloads": getattr(m, "downloads", 0),
                    "tags": list(getattr(m, "tags", []))[:5],
                }
                for m in models
            ]
        except Exception as e:
            logger.warning("HuggingFace search falhou: %s", e)
            return []

    async def _search_arxiv(
        self, query: str, max_results: int = 5
    ) -> list[dict]:
        """Busca artigos no Arxiv."""
        loop = asyncio.get_event_loop()
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )
            papers = await loop.run_in_executor(
                None,
                lambda: list(self._arxiv_client.results(search)),
            )
            return [
                {
                    "source": "arxiv",
                    "title": p.title,
                    "url": p.entry_id,
                    "description": p.summary[:300] if p.summary else "",
                    "authors": [a.name for a in p.authors[:3]],
                    "published": p.published.isoformat() if p.published else "",
                    "categories": p.categories,
                }
                for p in papers
            ]
        except Exception as e:
            logger.warning("Arxiv search falhou: %s", e)
            return []

    async def _crawl_url(self, url: str) -> str:
        """Faz crawl de uma URL usando crawl4ai."""
        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
            config = CrawlerRunConfig(
                cache_mode=CacheMode.ENABLED,
                word_count_threshold=50,
                remove_overlay_elements=True,
            )
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=url, config=config)
                if result.success:
                    return result.markdown[:3000]
                logger.warning("crawl4ai falhou em %s: %s", url, result.error_message)
                return ""
        except Exception as e:
            logger.warning("_crawl_url exception: %s", e)
            return ""

    # ─────────────────────────────────────────────
    # SÍNTESE VIA LLM
    # ─────────────────────────────────────────────

    async def _synthesize(self, query: str, results: list[dict]) -> str:
        """Sintetiza resultados da pesquisa usando LLM."""
        if not results:
            return "Nenhum resultado encontrado para a pesquisa."
        summaries = []
        for r in results[:15]:
            line = f"[{r['source'].upper()}] {r['title']}: {r.get('description', '')[:150]}"
            summaries.append(line)
        items_text = "\n".join(summaries)
        prompt = (
            f"Você é um assistente de pesquisa técnica do projeto The Moon Ecosystem.\n"
            f"Analise os resultados abaixo sobre: '{query}'\n\n"
            f"{items_text}\n\n"
            f"Gere um resumo técnico conciso (máx 300 palavras) destacando:\n"
            f"1. As descobertas mais relevantes\n"
            f"2. Tendências identificadas\n"
            f"3. Recomendações de ação para o projeto\n"
            f"Responda em português."
        )
        try:
            synthesis = await self._llm.complete(prompt, task_type="research", actor="deep_web_research_agent")
            return synthesis
        except Exception as e:
            logger.warning("LLM synthesis falhou: %s", e)
            tops = [r["title"] for r in results[:5]]
            return f"Top resultados para '{query}': {', '.join(tops)}"

    # ─────────────────────────────────────────────
    # MÉTODO PRINCIPAL
    # ─────────────────────────────────────────────

    async def research(
        self,
        query: str,
        sources: list[str] | None = None,
        max_per_source: int = 10,
        save_to_memory: bool = True,
    ) -> dict:
        """
        Executa pesquisa profunda em múltiplas fontes.

        Args:
            query: Termo de busca
            sources: Lista de fontes (github, huggingface, arxiv)
            max_per_source: Máximo de resultados por fonte
            save_to_memory: Se deve salvar no MemoryAgent

        Returns:
            Dicionário com resultados e síntese
        """
        sources = sources or _DEFAULT_SOURCES
        all_results: list[dict] = []

        tasks = []
        if "github" in sources:
            tasks.append(self._search_github(query, max_per_source))
        if "huggingface" in sources:
            tasks.append(self._search_huggingface(query, max_per_source))
        if "arxiv" in sources:
            tasks.append(self._search_arxiv(query, min(max_per_source, 10)))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for batch in gathered:
            if isinstance(batch, list):
                all_results.extend(batch)

        synthesis = await self._synthesize(query, all_results)

        payload = {
            "query": query,
            "sources_used": sources,
            "total_results": len(all_results),
            "results": all_results,
            "synthesis": synthesis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if save_to_memory:
            await self._bus.publish(
                "DeepWebResearchAgent",
                "memory.store",
                {
                    "content": f"Research: {query}\n\n{synthesis}",
                    "topic": "research",
                    "metadata": {
                        "query": query,
                        "sources": sources,
                        "total_results": len(all_results),
                    },
                },
            )

        return payload

    # ─────────────────────────────────────────────
    # MESSAGEBUS HANDLERS
    # ─────────────────────────────────────────────

    def _on_research_request_wrapper(self, message: Any) -> None:
        """Wrapper para receber mensagens do MessageBus."""
        sender = getattr(message, "sender", "unknown")
        payload = getattr(message, "payload", {})
        asyncio.create_task(self._on_research_request(sender, payload))

    async def _on_research_request(self, sender: str, payload: dict) -> None:
        """Handler para tópico research.request."""
        query = payload.get("query", "")
        if not query:
            logger.warning("research.request recebido sem query de %s", sender)
            return
        logger.info("Pesquisa iniciada: '%s' (de: %s)", query, sender)
        result = await self.research(
            query=query,
            sources=payload.get("sources", _DEFAULT_SOURCES),
            max_per_source=payload.get("max_per_source", 10),
            save_to_memory=payload.get("save_to_memory", True),
        )
        await self._bus.publish(
            "DeepWebResearchAgent",
            "research.result",
            result,
            target=sender,
        )
        logger.info(
            "Pesquisa concluída: '%s' — %d resultados",
            query, result["total_results"],
        )

    async def _heartbeat_loop(self) -> None:
        """Loop de heartbeat a cada 60 segundos."""
        while True:
            await asyncio.sleep(60)
            await self._bus.publish(
                "DeepWebResearchAgent",
                "hive.heartbeat",
                {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()},
            )

    # ─────────────────────────────────────────────
    # _execute — interface AgentBase
    # ─────────────────────────────────────────────

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """Executa tarefas de pesquisa."""
        start = time.time()
        try:
            if task == "research":
                query = kwargs.get("query")
                if not query:
                    return TaskResult(
                        success=False,
                        error="Parâmetro obrigatório ausente: 'query'",
                        execution_time=time.time() - start
                    )
                data = await self.research(
                    query=query,
                    sources=kwargs.get("sources"),
                    max_per_source=kwargs.get("max_per_source", 10),
                    save_to_memory=kwargs.get("save_to_memory", True),
                )
                return TaskResult(success=True, data=data,
                                  execution_time=time.time() - start)

            if task == "search_github":
                query = kwargs.get("query")
                if not query:
                    return TaskResult(
                        success=False,
                        error="Parâmetro obrigatório ausente: 'query'",
                        execution_time=time.time() - start
                    )
                data = await self._search_github(
                    query,
                    kwargs.get("max_results", 10),
                    kwargs.get("sort", "stars"),
                )
                return TaskResult(success=True, data={"results": data, "count": len(data)},
                                  execution_time=time.time() - start)

            if task == "search_huggingface":
                query = kwargs.get("query")
                if not query:
                    return TaskResult(
                        success=False,
                        error="Parâmetro obrigatório ausente: 'query'",
                        execution_time=time.time() - start
                    )
                data = await self._search_huggingface(
                    query,
                    kwargs.get("max_results", 10),
                )
                return TaskResult(success=True, data={"results": data, "count": len(data)},
                                  execution_time=time.time() - start)

            if task == "search_arxiv":
                query = kwargs.get("query")
                if not query:
                    return TaskResult(
                        success=False,
                        error="Parâmetro obrigatório ausente: 'query'",
                        execution_time=time.time() - start
                    )
                data = await self._search_arxiv(
                    query,
                    kwargs.get("max_results", 5),
                )
                return TaskResult(success=True, data={"results": data, "count": len(data)},
                                  execution_time=time.time() - start)

            if task == "crawl_url":
                url = kwargs.get("url")
                if not url:
                    return TaskResult(
                        success=False,
                        error="Parâmetro obrigatório ausente: 'url'",
                        execution_time=time.time() - start
                    )
                content = await self._crawl_url(url)
                return TaskResult(
                    success=bool(content),
                    data={"content": content, "url": url},
                    execution_time=time.time() - start,
                )

            return TaskResult(success=False, error=f"Task desconhecida: {task}",
                              execution_time=time.time() - start)

        except Exception as e:
            logger.exception("DeepWebResearchAgent._execute falhou: task=%s", task)
            return TaskResult(success=False, error=str(e),
                              execution_time=time.time() - start)
