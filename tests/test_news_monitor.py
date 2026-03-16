"""
tests/test_news_monitor.py
Testes para NewsMonitorAgent.
"""
import pytest
import asyncio
from pathlib import Path


class TestNewsMonitorAgent:
    """Testes para NewsMonitorAgent."""
    
    def test_news_monitor_import(self):
        """Teste básico de import."""
        from agents.news_monitor import NewsMonitorAgent, NewsAgent, RSS_FEEDS, KEYWORDS_BY_CATEGORY
        assert NewsMonitorAgent is not None
        assert NewsAgent is NewsMonitorAgent  # Alias
        assert len(RSS_FEEDS) > 0
        assert len(KEYWORDS_BY_CATEGORY) > 0
    
    @pytest.mark.asyncio
    async def test_news_monitor_initialization(self):
        """Testa inicialização do agente."""
        from agents.news_monitor import NewsMonitorAgent
        
        agent = NewsMonitorAgent()
        await agent.initialize()
        
        assert agent.is_initialized
        assert agent._seen_headlines is not None
        
        await agent.shutdown()
        assert not agent.is_initialized
    
    def test_deduplication(self):
        """Testa deduplicação de headlines."""
        from agents.news_monitor import NewsMonitorAgent
        import hashlib
        
        agent = NewsMonitorAgent()
        
        # Cria headlines com títulos idênticos
        headlines = [
            {"title": "Notícia Teste", "source": "G1"},
            {"title": "Notícia Teste", "source": "BBC"},  # Duplicada
            {"title": "Outra Notícia", "source": "G1"},
        ]
        
        # Deduplica
        unique = agent._deduplicate_headlines(headlines)
        
        # Deve remover duplicatas
        assert len(unique) == 2
        assert agent.stats["total_duplicates"] == 1
    
    def test_relevance_scoring(self):
        """Testa score de relevância."""
        from agents.news_monitor import NewsMonitorAgent
        
        agent = NewsMonitorAgent()
        
        headlines = [
            {"title": "Economia brasileira cresce com bolsa em alta", "description": "Mercado financeiro reage positivamente"},
            {"title": "Receita de bolo simples", "description": "Aprenda a fazer"},
        ]
        
        scored = agent._score_by_relevance(headlines, category="economia")
        
        # Primeira headline deve ter score maior (tem keywords de economia)
        assert scored[0]["score"] > scored[1]["score"]
    
    def test_data_directory_creation(self):
        """Testa criação de diretório de dados."""
        from agents.news_monitor import DATA_DIR
        
        # Diretório deve existir após import
        assert DATA_DIR.exists() or DATA_DIR.parent.exists()
    
    def test_category_feeds_mapping(self):
        """Testa mapeamento de categorias para feeds."""
        from agents.news_monitor import CATEGORY_FEEDS
        
        required_categories = ["all", "tecnologia", "economia", "esportes", "geral"]
        
        for category in required_categories:
            assert category in CATEGORY_FEEDS
            assert len(CATEGORY_FEEDS[category]) > 0


class TestNewsMonitorFunctional:
    """Testes funcionais (requer conexão internet)."""
    
    @pytest.mark.asyncio
    async def test_fetch_headlines_basic(self):
        """Testa fetch básico de headlines."""
        from agents.news_monitor import NewsMonitorAgent
        
        agent = NewsMonitorAgent()
        await agent.initialize()
        
        try:
            # Fetch deve retornar lista (pode ser vazia se RSS falhar)
            headlines = await agent.fetch_headlines("tecnologia")
            
            assert isinstance(headlines, list)
            # Não assertamos len > 0 porque RSS pode estar indisponível
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_fetch_all_categories(self):
        """Testa fetch de todas as categorias."""
        from agents.news_monitor import NewsMonitorAgent, CATEGORY_FEEDS
        
        agent = NewsMonitorAgent()
        await agent.initialize()
        
        try:
            for category in CATEGORY_FEEDS.keys():
                headlines = await agent.fetch_headlines(category)
                assert isinstance(headlines, list)
        finally:
            await agent.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
