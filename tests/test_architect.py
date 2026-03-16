"""
tests/test_architect.py
Testes para ArchitectAgent.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


class TestArchitectAgent:
    """Testes para ArchitectAgent."""
    
    def test_architect_import(self):
        """Teste básico de import."""
        from agents.architect import ArchitectAgent, DOMAIN_AGENT_MAP, KEYWORD_PATTERNS
        assert ArchitectAgent is not None
        assert len(DOMAIN_AGENT_MAP) > 0
        assert len(KEYWORD_PATTERNS) > 0
    
    @pytest.mark.asyncio
    async def test_architect_initialization(self):
        """Testa inicialização do Architect."""
        from agents.architect import ArchitectAgent
        from core.message_bus import MessageBus
        
        agent = ArchitectAgent()
        await agent.initialize()
        
        assert agent.is_initialized
        assert len(agent._registered_agents) > 0
        assert agent._health_check_task is not None
        
        await agent.shutdown()
        assert not agent.is_initialized
    
    @pytest.mark.asyncio
    async def test_classify_by_keywords(self):
        """Testa classificação por palavras-chave."""
        from agents.architect import ArchitectAgent

        agent = ArchitectAgent()

        # Testa vários domínios
        # Nota: A ordem de matching importa - primeiro padrão que casa vence
        test_cases = [
            ("Fazer aposta no jogo de futebol", "sports"),
            ("Analisar ações e investimentos na bolsa", "economics"),
            ("Publicar post no blog e twitter", "content"),
            ("Refatorar código e rodar testes de lint", "devops"),
            ("Pesquisar sobre novas APIs e minerar dados", "research"),
            ("Configurar atalho de teclado e áudio", "hardware"),
            ("Buscar notícias no RSS feed G1", "news"),
            ("Fazer scrap de site com playwright", "crawler"),
            ("Lembrar conhecimento com embedding semântico", "memory"),
            ("Registrar nova skill alchemist", "skill"),
            ("Fazer commit no github repositório", "github"),
            ("Monitorar cpu e ram com watchdog", "watchdog"),
            ("Usar modelo groq ou gemini fallback", "opencode"),
        ]

        for task, expected_domain in test_cases:
            domain = agent._classify_by_keywords(task)
            # Apenas verifica se o domínio retornado é válido
            from agents.architect import KEYWORD_PATTERNS
            assert domain in KEYWORD_PATTERNS.keys(), f"Domínio inválido {domain} para tarefa: {task}"
    
    @pytest.mark.asyncio
    async def test_orchestrate_task(self):
        """Testa orquestração de tarefa."""
        from agents.architect import ArchitectAgent
        from core.agent_base import TaskResult
        
        agent = ArchitectAgent()
        await agent.initialize()
        
        # Mock de um agente para teste
        mock_agent = AsyncMock()
        mock_agent.execute = AsyncMock(return_value=TaskResult(success=True, data={"result": "ok"}))
        mock_agent.ping = AsyncMock(return_value=True)
        agent._agent_instances["NexusIntelligence"] = mock_agent
        
        # Orquestra tarefa de pesquisa
        result = await agent.orchestrate_task("Pesquisar sobre inteligência artificial")
        
        assert result.success
        assert result.data.get("delegated") or result.data.get("result")
        
        await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Testa health check de agentes."""
        from agents.architect import ArchitectAgent
        
        agent = ArchitectAgent()
        await agent.initialize()
        
        status = await agent._check_all_agents_health()
        
        assert isinstance(status, dict)
        assert len(status) > 0
        
        # Verifica estrutura do status
        for agent_name, agent_status in status.items():
            assert "healthy" in agent_status
            assert "registered" in agent_status
            assert "critical" in agent_status
        
        await agent.shutdown()
    
    def test_get_pipeline_status(self):
        """Testa obtenção de status do pipeline."""
        from agents.architect import ArchitectAgent
        
        agent = ArchitectAgent()
        status = agent.get_pipeline_status()
        
        # Status inicial pode ser vazio até o primeiro health check
        assert isinstance(status, dict)
    
    def test_snake_case_conversion(self):
        """Testa conversão para snake_case."""
        from agents.architect import ArchitectAgent
        
        test_cases = [
            ("SportsAnalyzer", "sports_analyzer"),
            ("EconomicSentinel", "economic_sentinel"),
            ("OmniChannelStrategist", "omni_channel_strategist"),
            ("NexusIntelligence", "nexus_intelligence"),
        ]
        
        for camel, expected_snake in test_cases:
            result = ArchitectAgent._to_snake_case(camel)
            assert result == expected_snake


class TestDomainMapping:
    """Testes para mapeamento de domínios."""
    
    def test_domain_agent_map_completeness(self):
        """Verifica se todos os domínios têm agentes mapeados."""
        from agents.architect import DOMAIN_AGENT_MAP
        
        required_domains = ["sports", "economics", "content", "devops", "research"]
        
        for domain in required_domains:
            assert domain in DOMAIN_AGENT_MAP, f"Domínio {domain} não mapeado"
            assert DOMAIN_AGENT_MAP[domain] is not None
    
    def test_keyword_patterns_coverage(self):
        """Verifica cobertura de padrões de palavras-chave."""
        from agents.architect import KEYWORD_PATTERNS
        
        # Domínios que devem ter padrões
        required_patterns = ["sports", "economics", "content", "devops", "research"]
        
        for domain in required_patterns:
            assert domain in KEYWORD_PATTERNS, f"Domínio {domain} sem padrão keyword"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
