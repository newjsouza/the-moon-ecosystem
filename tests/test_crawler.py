"""
tests/test_crawler.py
Testes para CrawlerAgent.
"""
import pytest
import asyncio
from pathlib import Path


class TestCrawlerAgent:
    """Testes para CrawlerAgent."""
    
    def test_crawler_import(self):
        """Teste básico de import."""
        from agents.crawler import CrawlerAgent, WebCrawler, USER_AGENTS, PLAYWRIGHT_AVAILABLE
        assert CrawlerAgent is not None
        assert WebCrawler is CrawlerAgent  # Alias
        assert len(USER_AGENTS) > 0
        assert isinstance(PLAYWRIGHT_AVAILABLE, bool)
    
    @pytest.mark.asyncio
    async def test_crawler_initialization(self):
        """Testa inicialização do agente."""
        from agents.crawler import CrawlerAgent
        
        agent = CrawlerAgent()
        await agent.initialize()
        
        assert agent.is_initialized
        assert agent.stats["total_crawled"] == 0
        
        await agent.shutdown()
        assert not agent.is_initialized
    
    def test_user_agent_rotation(self):
        """Testa rotation de User-Agent."""
        from agents.crawler import CrawlerAgent, USER_AGENTS
        
        agent = CrawlerAgent()
        
        # Testa múltiplas chamadas
        uas = [agent._get_next_user_agent() for _ in range(len(USER_AGENTS) * 2)]
        
        # Deve ciclar através da lista
        assert len(set(uas)) == len(USER_AGENTS)
    
    def test_rate_limit_logic(self):
        """Testa lógica de rate limiting."""
        from agents.crawler import CrawlerAgent
        import time
        
        agent = CrawlerAgent()
        
        # Primeiro request não deve delay
        start = time.time()
        asyncio.run(agent._enforce_rate_limit("http://example.com"))
        elapsed1 = time.time() - start
        
        # Segundo request imediato deve ter delay
        start = time.time()
        asyncio.run(agent._enforce_rate_limit("http://example.com"))
        elapsed2 = time.time() - start
        
        # Segundo request deve ter aguardado
        assert elapsed2 > 0.5  # Pelo menos parte do delay
    
    def test_data_directory_creation(self):
        """Testa criação de diretório de dados."""
        from agents.crawler import DATA_DIR
        
        # Diretório pai deve existir
        assert DATA_DIR.parent.exists()
    
    def test_url_parsing(self):
        """Testa parsing de URL para domain extraction."""
        from urllib.parse import urlparse
        
        test_cases = [
            ("https://g1.globo.com/tecnologia", "g1.globo.com"),
            ("http://example.com/path", "example.com"),
            ("https://www.bbc.com/portuguese", "www.bbc.com"),
        ]
        
        for url, expected_domain in test_cases:
            domain = urlparse(url).netloc
            assert domain == expected_domain


class TestCrawlerFunctional:
    """Testes funcionais (requer conexão internet)."""
    
    @pytest.mark.asyncio
    async def test_crawl_simple_url(self):
        """Testa crawl de URL simples."""
        from agents.crawler import CrawlerAgent
        
        agent = CrawlerAgent()
        await agent.initialize()
        
        try:
            # URL de teste simples (exemplo)
            result = await agent.crawl_url("https://example.com", extract="text")
            
            assert result["success"]
            assert result["url"] == "https://example.com"
            assert "title" in result
            assert "Example Domain" in result.get("title", "")
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_crawl_with_different_extracts(self):
        """Testa diferentes tipos de extração."""
        from agents.crawler import CrawlerAgent
        
        agent = CrawlerAgent()
        await agent.initialize()
        
        try:
            url = "https://example.com"
            
            # Testa extract "text"
            result_text = await agent.crawl_url(url, extract="text")
            assert "body" in result_text or result_text.get("success")
            
            # Testa extract "links"
            result_links = await agent.crawl_url(url, extract="links")
            assert "internal_links" in result_links or result_links.get("success")
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_crawl_batch(self):
        """Testa crawl em lote."""
        from agents.crawler import CrawlerAgent
        
        agent = CrawlerAgent()
        await agent.initialize()
        
        try:
            urls = [
                "https://example.com",
                "https://example.org",
            ]
            
            results = await agent.crawl_batch(urls, concurrency=2)
            
            assert len(results) == 2
            assert all(isinstance(r, dict) for r in results)
            
        finally:
            await agent.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
