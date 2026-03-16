"""
agents/news_monitor.py
Monitoramento contínuo de notícias e tendências.

Fontes de Dados (todas gratuitas/sem autenticação):
  - RSS Feeds: G1, BBC Brasil, Reuters, ESPN
  - API pública NewsData.io (free tier — usar variável NEWSDATA_API_KEY do .env)
  - Fallback sem API: parsing de RSS puro via feedparser

Funcionalidades:
  - fetch_headlines(category): busca top 20 headlines
  - monitor_continuous(interval_seconds): loop de monitoramento a cada 5 min
  - Deduplicação por hash SHA256 do título
  - Persistência local em data/news/headlines_YYYY-MM-DD.json
  - Publicação no tópico "news.headline_batch" da MessageBus

Filtragem Inteligente:
  - Filtra por palavras-chave (configurável via config/news_keywords.yaml)
  - Categorias padrão: economia, esportes, tecnologia, política, IA
  - Score de relevância simples (contagem de keywords no título + descrição)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiohttp
import feedparser

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus
from core.config import Config
from utils.logger import setup_logger

logger = setup_logger("NewsMonitorAgent")

# ─────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────
DEFAULT_MONITOR_INTERVAL = 300  # 5 minutos
MAX_HEADLINES_PER_FETCH = 20
DATA_DIR = Path("data/news")

# ─────────────────────────────────────────────────────────────
#  RSS Feeds (gratuitos, sem autenticação)
# ─────────────────────────────────────────────────────────────
RSS_FEEDS = {
    "g1": "https://g1.globo.com/rss/g1/",
    "g1_tecnologia": "https://g1.globo.com/rss/tecnologia/",
    "g1_economia": "https://g1.globo.com/rss/economia/",
    "g1_esportes": "https://g1.globo.com/rss/esportes/",
    "bbc_brasil": "https://feeds.bbci.co.uk/portuguese/world/rss.xml",
    "reuters_top_news": "https://www.reutersagency.com/feed/top-news/",
    "reuters_business": "https://www.reutersagency.com/feed/business/",
    "espn": "https://www.espn.com/espn/feed/news",
}

# Mapeamento de categorias para feeds
CATEGORY_FEEDS = {
    "all": list(RSS_FEEDS.values()),
    "tecnologia": [RSS_FEEDS["g1_tecnologia"]],
    "economia": [RSS_FEEDS["g1_economia"], RSS_FEEDS["reuters_business"]],
    "esportes": [RSS_FEEDS["g1_esportes"], RSS_FEEDS["espn"]],
    "geral": [RSS_FEEDS["g1"], RSS_FEEDS["bbc_brasil"], RSS_FEEDS["reuters_top_news"]],
    "politica": [RSS_FEEDS["bbc_brasil"], RSS_FEEDS["g1"]],
}

# ─────────────────────────────────────────────────────────────
#  Palavras-chave por categoria (filtragem inteligente)
# ─────────────────────────────────────────────────────────────
KEYWORDS_BY_CATEGORY = {
    "economia": ["economia", "mercado", "bolsa", "investimento", "financeiro", "banco", "crypto", "bitcoin", "dólar", "real"],
    "esportes": ["futebol", "esporte", "jogo", "partida", "gol", "campeonato", "time", "atleta", "olimpíada"],
    "tecnologia": ["tecnologia", "ia", "inteligência artificial", "software", "hardware", "startup", "app", "google", "microsoft", "apple"],
    "politica": ["política", "governo", "presidente", "congresso", "senado", "eleição", "ministro", "supremo"],
    "ia": ["ia", "inteligência artificial", "machine learning", "deep learning", "llm", "gpt", "modelo", "neural"],
}


class NewsMonitorAgent(AgentBase):
    """
    Agente de monitoramento contínuo de notícias.
    
    Responsabilidades:
      - Coletar headlines de múltiplas fontes (RSS + API)
      - Deduplicar por hash SHA256
      - Filtrar por relevância (keywords)
      - Persistir localmente
      - Publicar na MessageBus
    """

    def __init__(self, message_bus: Optional[MessageBus] = None) -> None:
        super().__init__()
        self.name = "NewsMonitorAgent"
        self.description = "Monitoramento contínuo de notícias e tendências."
        self.priority = AgentPriority.MEDIUM

        self._config = Config()
        self._message_bus = message_bus or MessageBus()

        # Cache de headlines já vistas (hash SHA256)
        self._seen_headlines: Set[str] = set()

        # Loop de monitoramento
        self._stop_event = asyncio.Event()
        self._monitor_task: Optional[asyncio.Task] = None

        # Estatísticas
        self.stats = {
            "total_fetched": 0,
            "total_duplicates": 0,
            "total_published": 0,
            "last_fetch_time": None
        }

        # Garantir diretório de dados
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        """Inicializa o agente e carrega histórico de headlines."""
        await super().initialize()
        await self._load_seen_headlines()
        logger.info("NewsMonitorAgent initialized.")

    async def shutdown(self) -> None:
        """Encerra loop de monitoramento."""
        self._stop_event.set()
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        await super().shutdown()
        logger.info("NewsMonitorAgent shut down.")

    # ═══════════════════════════════════════════════════════════
    #  Execute Dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, action: str, **kwargs: Any) -> TaskResult:
        """
        Ações suportadas:
          fetch: Busca headlines (kwargs: category)
          monitor: Inicia monitoramento contínuo (kwargs: interval_seconds)
          stop: Para monitoramento
          status: Retorna estatísticas
        """
        match action:
            case "fetch":
                category = kwargs.get("category", "all")
                headlines = await self.fetch_headlines(category)
                return TaskResult(
                    success=True,
                    data={
                        "headlines": headlines,
                        "count": len(headlines),
                        "category": category
                    }
                )

            case "monitor":
                interval = kwargs.get("interval_seconds", DEFAULT_MONITOR_INTERVAL)
                await self.monitor_continuous(interval)
                return TaskResult(
                    success=True,
                    data={"monitoring": True, "interval": interval}
                )

            case "stop":
                await self.stop_monitoring()
                return TaskResult(success=True, data={"monitoring": False})

            case "status":
                return TaskResult(
                    success=True,
                    data={
                        "stats": self.stats,
                        "monitoring": not self._stop_event.is_set()
                    }
                )

            case _:
                return TaskResult(
                    success=False,
                    error=f"Ação desconhecida: '{action}'"
                )

    # ═══════════════════════════════════════════════════════════
    #  Fetch de Headlines
    # ═══════════════════════════════════════════════════════════

    async def fetch_headlines(self, category: str = "all") -> List[Dict[str, Any]]:
        """
        Busca top 20 headlines de uma categoria.
        
        Args:
            category: Categoria ("all", "tecnologia", "economia", "esportes", etc.)
        
        Returns:
            Lista de headlines com título, fonte, link, data e score de relevância
        """
        logger.info(f"Buscando headlines para categoria: {category}")
        
        all_headlines = []
        
        # Tenta API NewsData.io primeiro (se disponível)
        api_key = self._config.get("newsdata.api_key") or os.getenv("NEWSDATA_API_KEY")
        if api_key and api_key != "COLE_O_SEU_TOKEN_AQUI":
            try:
                api_headlines = await self._fetch_from_newsdata_api(api_key, category)
                all_headlines.extend(api_headlines)
            except Exception as e:
                logger.warning(f"NewsData.io API falhou: {e}. Usando fallback RSS.")
        
        # Fallback/Complemento: RSS Feeds
        feeds = CATEGORY_FEEDS.get(category, CATEGORY_FEEDS["all"])
        rss_headlines = await self._fetch_from_rss(feeds)
        all_headlines.extend(rss_headlines)
        
        # Deduplicação
        unique_headlines = self._deduplicate_headlines(all_headlines)
        
        # Filtra por relevância (keywords)
        scored_headlines = self._score_by_relevance(unique_headlines, category)
        
        # Ordena por score e retorna top N
        scored_headlines.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_headlines = scored_headlines[:MAX_HEADLINES_PER_FETCH]
        
        # Atualiza estatísticas
        self.stats["total_fetched"] += len(top_headlines)
        self.stats["last_fetch_time"] = time.time()
        
        # Persiste localmente
        await self._persist_headlines(top_headlines)
        
        # Publica na MessageBus
        await self._publish_headlines(top_headlines)
        
        logger.info(f"{len(top_headlines)} headlines obtidas com sucesso.")
        return top_headlines

    async def _fetch_from_newsdata_api(
        self,
        api_key: str,
        category: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Busca headlines via NewsData.io API.
        """
        url = "https://newsdata.io/api/1/latest"
        params = {
            "apikey": api_key,
            "language": "pt",
            "max_results": 20
        }
        
        # Mapeia categoria para país/região
        if category == "economia":
            params["category"] = "business"
        elif category == "esportes":
            params["category"] = "sports"
        elif category == "tecnologia":
            params["category"] = "technology"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    headlines = []
                    for article in data.get("results", []):
                        headlines.append({
                            "title": article.get("title", "Sem título"),
                            "description": article.get("description", ""),
                            "source": article.get("source_id", "newsdata"),
                            "link": article.get("link", ""),
                            "published_at": article.get("pubDate", ""),
                            "category": category,
                        })
                    return headlines
                else:
                    logger.warning(f"NewsData.io retornou status {resp.status}")
                    return []

    async def _fetch_from_rss(self, feed_urls: List[str]) -> List[Dict[str, Any]]:
        """
        Busca headlines de múltiplos feeds RSS.
        """
        headlines = []
        
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_single_rss(session, url) for url in feed_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, list):
                    headlines.extend(result)
                elif isinstance(result, Exception):
                    logger.warning(f"Erro ao fetch RSS: {result}")
        
        return headlines

    async def _fetch_single_rss(
        self,
        session: aiohttp.ClientSession,
        feed_url: str
    ) -> List[Dict[str, Any]]:
        """
        Busca headlines de um único feed RSS.
        """
        try:
            async with session.get(feed_url, timeout=30) as resp:
                if resp.status != 200:
                    return []
                
                xml_content = await resp.text()
                feed = feedparser.parse(xml_content)
                
                headlines = []
                for entry in feed.entries[:10]:  # Top 10 por feed
                    headlines.append({
                        "title": entry.get("title", "Sem título"),
                        "description": entry.get("description", entry.get("summary", "")),
                        "source": feed.feed.get("title", "RSS"),
                        "link": entry.get("link", ""),
                        "published_at": entry.get("published", ""),
                        "category": "geral",
                    })
                
                return headlines
                
        except Exception as e:
            logger.debug(f"Erro ao fetch RSS {feed_url}: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    #  Deduplicação e Filtragem
    # ═══════════════════════════════════════════════════════════

    def _deduplicate_headlines(
        self,
        headlines: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Remove headlines duplicadas por hash SHA256 do título.
        """
        unique = []
        
        for headline in headlines:
            title = headline.get("title", "")
            title_hash = hashlib.sha256(title.encode()).hexdigest()
            
            if title_hash not in self._seen_headlines:
                self._seen_headlines.add(title_hash)
                headline["_hash"] = title_hash
                unique.append(headline)
            else:
                self.stats["total_duplicates"] += 1
        
        return unique

    def _score_by_relevance(
        self,
        headlines: List[Dict[str, Any]],
        category: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Calcula score de relevância baseado em keywords.
        """
        # Coleta keywords da categoria + todas as outras
        keywords = set()
        if category in KEYWORDS_BY_CATEGORY:
            keywords.update(KEYWORDS_BY_CATEGORY[category])
        
        # Se categoria é "all", usa todas as keywords
        if category == "all":
            for cat_keywords in KEYWORDS_BY_CATEGORY.values():
                keywords.update(cat_keywords)
        
        scored = []
        for headline in headlines:
            title_lower = headline.get("title", "").lower()
            desc_lower = headline.get("description", "").lower()
            text = f"{title_lower} {desc_lower}"
            
            # Conta matches de keywords
            score = sum(1 for kw in keywords if kw.lower() in text)
            headline["score"] = score
            headline["matched_keywords"] = [
                kw for kw in keywords if kw.lower() in text
            ][:5]  # Top 5 keywords
            
            scored.append(headline)
        
        return scored

    # ═══════════════════════════════════════════════════════════
    #  Monitoramento Contínuo
    # ═══════════════════════════════════════════════════════════

    async def monitor_continuous(self, interval_seconds: int = DEFAULT_MONITOR_INTERVAL) -> None:
        """
        Inicia loop de monitoramento contínuo.
        """
        if not self._stop_event.is_set():
            logger.warning("Monitoramento já está em execução.")
            return
        
        self._stop_event.clear()
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(interval_seconds),
            name="moon.news_monitor.loop"
        )
        logger.info(f"Monitoramento iniciado (intervalo: {interval_seconds}s)")

    async def _monitor_loop(self, interval_seconds: int) -> None:
        """
        Loop de monitoramento em background.
        """
        logger.info("Loop de monitoramento de notícias iniciado.")
        
        while not self._stop_event.is_set():
            try:
                # Fetch de headlines
                headlines = await self.fetch_headlines("all")
                
                # Filtra apenas headlines de alta relevância (score >= 2)
                high_relevance = [h for h in headlines if h.get("score", 0) >= 2]
                
                if high_relevance:
                    logger.info(f"{len(high_relevance)} headlines de alta relevância encontradas.")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no monitor loop: {e}")
            
            # Aguarda próximo ciclo
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=interval_seconds
                )
                break  # stop_event foi setado
            except asyncio.TimeoutError:
                pass  # Continua loop
        
        logger.info("Loop de monitoramento encerrado.")

    async def stop_monitoring(self) -> None:
        """Para o loop de monitoramento."""
        self._stop_event.set()
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Monitoramento parado.")

    # ═══════════════════════════════════════════════════════════
    #  Persistência e Publicação
    # ═══════════════════════════════════════════════════════════

    async def _persist_headlines(self, headlines: List[Dict[str, Any]]) -> None:
        """
        Persiste headlines localmente em JSON.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = DATA_DIR / f"headlines_{today}.json"
        
        # Carrega existentes
        existing = []
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        
        # Adiciona novas (sem duplicar por hash)
        existing_hashes = {h.get("_hash") for h in existing}
        for headline in headlines:
            if headline.get("_hash") not in existing_hashes:
                # Remove hash interno antes de persistir
                headline_clean = {k: v for k, v in headline.items() if not k.startswith("_")}
                existing.append(headline_clean)
        
        # Salva
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Headlines persistidas em {filepath}")

    async def _load_seen_headlines(self) -> None:
        """
        Carrega hashes de headlines já vistas (para deduplicação).
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = DATA_DIR / f"headlines_{today}.json"
        
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    headlines = json.load(f)
                
                # Recria hashes
                for headline in headlines:
                    title = headline.get("title", "")
                    title_hash = hashlib.sha256(title.encode()).hexdigest()
                    self._seen_headlines.add(title_hash)
                
                logger.info(f"{len(self._seen_headlines)} headlines carregadas para deduplicação.")
            except Exception as e:
                logger.warning(f"Erro ao carregar headlines: {e}")

    async def _publish_headlines(self, headlines: List[Dict[str, Any]]) -> None:
        """
        Publica headlines na MessageBus.
        """
        if not headlines:
            return
        
        try:
            await self._message_bus.publish(
                sender=self.name,
                topic="news.headline_batch",
                payload={
                    "headlines": headlines,
                    "count": len(headlines),
                    "timestamp": time.time()
                }
            )
            self.stats["total_published"] += len(headlines)
        except Exception as e:
            logger.debug(f"Não foi possível publicar headlines: {e}")


# Alias para compatibilidade
NewsAgent = NewsMonitorAgent
