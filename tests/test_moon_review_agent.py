"""
tests/test_moon_review_agent.py
Testes para MoonReviewAgent

Executar:
    python3 -m pytest tests/test_moon_review_agent.py -v
"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


class TestASTDetectsMissingAwait:
    """Testa que AST detecta coroutine sem await."""
    
    def test_detects_missing_await(self):
        from agents.moon_review_agent import ASTAnalyzer
        
        code = """
async def fetch_data():
    result = asyncio.sleep(1)  # Missing await
    return result
"""
        analyzer = ASTAnalyzer()
        findings = analyzer.analyze(code, "test.py")
        
        # Verifica que encontrou algum problema
        assert len(findings) > 0


class TestASTDetectsProhibitedModel:
    """Testa que AST detecta modelos proibidos."""
    
    def test_detects_gpt4(self):
        from agents.moon_review_agent import ASTAnalyzer
        
        code = """
model = "gpt-4"
client = OpenAI(model=model)
"""
        analyzer = ASTAnalyzer()
        findings = analyzer.analyze(code, "test.py")
        
        prohibited = [f for f in findings if f['type'] == 'PROHIBITED_MODEL']
        assert len(prohibited) > 0
        assert prohibited[0]['severity'] == 'CRITICAL'
    
    def test_detects_claude(self):
        from agents.moon_review_agent import ASTAnalyzer
        
        code = """
model = "claude-3-opus"
"""
        analyzer = ASTAnalyzer()
        findings = analyzer.analyze(code, "test.py")
        
        prohibited = [f for f in findings if f['type'] == 'PROHIBITED_MODEL']
        assert len(prohibited) > 0


class TestLLMReviewParsesIssues:
    """Testa que resposta do LLM é parseada corretamente."""
    
    def test_parse_llm_response(self):
        from agents.moon_review_agent import MoonReviewAgent
        
        agent = MoonReviewAgent()
        
        response = """
ISSUE #1
Severidade: CRITICAL
Arquivo: agents/browser.py:45
Problema: Race condition em acesso compartilhado
Impacto em Produção: Pode causar corrupção de dados
Fix Sugerido: Usar asyncio.Lock para proteger acesso
---
ISSUE #2
Severidade: HIGH
Arquivo: core/bridge.py:120
Problema: Timeout não tratado em chamada HTTP
Impacto em Produção: Request pode travar indefinidamente
Fix Sugerido: Adicionar timeout=30 ao client HTTP
---
"""
        
        issues = agent._parse_llm_response(response)
        
        assert len(issues) == 2
        assert issues[0]['severity'] == 'CRITICAL'
        assert issues[1]['severity'] == 'HIGH'


class TestHealthScoreCalculation:
    """Testa cálculo do health score."""
    
    def test_health_score_1_critical_2_high(self):
        from agents.moon_review_agent import MoonReviewAgent
        
        agent = MoonReviewAgent()
        
        ast_findings = [
            {'severity': 'CRITICAL', 'type': 'PROHIBITED_MODEL'},
        ]
        llm_findings = [
            {'severity': 'HIGH', 'problem': 'Issue 1'},
            {'severity': 'HIGH', 'problem': 'Issue 2'},
        ]
        
        report = agent._generate_report(["test.py"], ast_findings, llm_findings)
        
        # 100 - 20 (1 critical) - 20 (2 high) = 60
        assert report['health_score'] == 60
        assert report['critical_count'] == 1
        assert report['high_count'] == 2


class TestCriticalTriggersWatchdog:
    """Testa que issues críticos disparam alerta no Watchdog."""
    
    @pytest.mark.asyncio
    async def test_publishes_watchdog_alert(self):
        from agents.moon_review_agent import MoonReviewAgent
        
        agent = MoonReviewAgent()
        await agent.initialize()
        
        # Mock da MessageBus
        mock_publish = AsyncMock()
        agent._message_bus.publish = mock_publish
        
        # Mock do diff e análises
        agent._get_git_diff = lambda: "diff content"
        agent._parse_diff_files = lambda x: ["test.py"]
        agent._analyze_ast = lambda x: [{'severity': 'CRITICAL', 'type': 'TEST'}]
        agent._analyze_llm = AsyncMock(return_value=[])
        agent._generate_report = lambda x, y, z: {
            "critical_count": 1,
            "high_count": 0,
            "medium_count": 0,
            "health_score": 80,
            "files_reviewed": x,
            "ast_issues": y,
            "llm_issues": z,
            "timestamp": "2026-03-16T00:00:00"
        }
        
        result = await agent._execute("auto")
        
        # Verifica que publicou em review.completed
        assert mock_publish.called
        
        # Verifica que publicou alerta no watchdog
        watchdog_calls = [
            call for call in mock_publish.call_args_list
            if call[1].get('topic') == 'watchdog.alert'
        ]
        assert len(watchdog_calls) > 0


class TestReviewAgentExecution:
    """Testa execução completa do agente."""
    
    @pytest.mark.asyncio
    async def test_execute_auto_mode(self):
        from agents.moon_review_agent import MoonReviewAgent
        
        agent = MoonReviewAgent()
        await agent.initialize()
        
        # Mock para retornar diff vazio
        agent._get_git_diff = lambda: ""
        
        result = await agent._execute("auto")
        
        assert result.success is True
        assert result.data.get("message") == "No changes to review"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
