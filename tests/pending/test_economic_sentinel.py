"""
tests/test_economic_sentinel.py
Testes para EconomicSentinel (Inteligência Financeira).

Cobertura:
  - Coleta e normalização de dados
  - Tratamento de falha de provider
  - Geração de relatório JSON
  - Cálculo de tendência/médias
  - Publicação no tópico correto da MessageBus
  - Comportamento com payload vazio ou parcialmente inválido
"""
import pytest
import os
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from agents.economic_sentinel import (
    EconomicSentinel,
    FinancialEngine,
    MarketAnalyzer,
)
from core.agent_base import TaskResult


# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def sentinel():
    """Cria instância do EconomicSentinel para testes."""
    return EconomicSentinel()


@pytest.fixture
def sentinel_with_message_bus(mock_message_bus):
    """Cria EconomicSentinel com MessageBus mockado."""
    sentinel = EconomicSentinel()
    sentinel.message_bus = mock_message_bus
    return sentinel


@pytest.fixture
def mock_yfinance_ticker():
    """Mock para yfinance.Ticker."""
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "regularMarketPrice": 150.25,
        "regularMarketChangePercent": 2.5,
        "currency": "USD",
        "symbol": "AAPL",
    }
    return mock_ticker


@pytest.fixture
def mock_alpha_vantage_timeseries():
    """Mock para alpha_vantage.timeseries."""
    mock_ts = MagicMock()
    # Retorna DataFrame mockado
    import pandas as pd
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    data = pd.DataFrame({
        '4. close': [100 + i * 0.5 for i in range(30)]
    }, index=dates)
    mock_ts.get_daily = MagicMock(return_value=(data, MagicMock()))
    return mock_ts


# ─────────────────────────────────────────────────────────────
#  Testes de Import e Inicialização
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_economic_sentinel_import():
    """Teste básico de import do EconomicSentinel."""
    from agents.economic_sentinel import EconomicSentinel, FinancialEngine, MarketAnalyzer
    assert EconomicSentinel is not None
    assert FinancialEngine is not None
    assert MarketAnalyzer is not None


@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_sentinel_initialization(sentinel):
    """Testa inicialização básica do EconomicSentinel."""
    assert sentinel.name == "EconomicSentinel"
    assert sentinel.api_key is not None  # Pode ser "demo"
    assert sentinel.engine is not None
    assert sentinel.analyzer is not None


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_sentinel_initialize(sentinel):
    """Testa método initialize do EconomicSentinel."""
    result = await sentinel.initialize()
    assert result is True


# ─────────────────────────────────────────────────────────────
#  Testes do FinancialEngine
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_financial_engine_initialization():
    """Testa inicialização do FinancialEngine."""
    engine = FinancialEngine(api_key="test_key")
    assert engine.api_key == "test_key"


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_get_market_summary_success(mock_yfinance_ticker):
    """Testa coleta de resumo de mercado com sucesso."""
    with patch('yfinance.Ticker', return_value=mock_yfinance_ticker):
        engine = FinancialEngine(api_key="test_key")
        summary = await engine.get_market_summary(["AAPL"])
        
        assert "AAPL" in summary
        assert summary["AAPL"]["price"] == 150.25
        assert summary["AAPL"]["change"] == 2.5
        assert summary["AAPL"]["currency"] == "USD"


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_get_market_summary_error_handling():
    """Testa tratamento de erro ao coletar dados de mercado."""
    with patch('yfinance.Ticker') as mock_ticker:
        mock_ticker.side_effect = Exception("API Error")
        
        engine = FinancialEngine(api_key="test_key")
        summary = await engine.get_market_summary(["INVALID"])
        
        assert "INVALID" in summary
        assert "error" in summary["INVALID"]


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_get_market_summary_empty_symbols():
    """Testa coleta com lista vazia de símbolos."""
    engine = FinancialEngine(api_key="test_key")
    summary = await engine.get_market_summary([])
    
    assert summary == {}


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_alpha_vantage_data_success(mock_alpha_vantage_timeseries):
    """Testa coleta de dados da Alpha Vantage com sucesso."""
    with patch('alpha_vantage.timeseries.TimeSeries', return_value=mock_alpha_vantage_timeseries):
        engine = FinancialEngine(api_key="test_key")
        data = await engine.get_alpha_vantage_data("AAPL")
        
        assert not data.empty
        assert '4. close' in data.columns


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_alpha_vantage_data_error():
    """Testa tratamento de erro na Alpha Vantage."""
    with patch('alpha_vantage.timeseries.TimeSeries') as mock_ts:
        mock_ts.side_effect = Exception("API Limit")
        
        engine = FinancialEngine(api_key="test_key")
        data = await engine.get_alpha_vantage_data("AAPL")
        
        assert data.empty


# ─────────────────────────────────────────────────────────────
#  Testes do MarketAnalyzer
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_analyzer_initialization():
    """Testa inicialização do MarketAnalyzer."""
    analyzer = MarketAnalyzer()
    assert analyzer is not None


@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_analyze_trends_bullish():
    """Testa análise de tendência de alta."""
    import pandas as pd
    
    # Cria dados com tendência de alta
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    data = pd.DataFrame({
        '4. close': [100 + i * 2 for i in range(30)]  # Tendência clara de alta
    }, index=dates)
    
    analyzer = MarketAnalyzer()
    trend = analyzer.analyze_trends(data)
    
    assert "ALTA" in trend or "Bullish" in trend


@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_analyze_trends_bearish():
    """Testa análise de tendência de baixa."""
    import pandas as pd
    
    # Cria dados com tendência de baixa
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    data = pd.DataFrame({
        '4. close': [200 - i * 2 for i in range(30)]  # Tendência clara de baixa
    }, index=dates)
    
    analyzer = MarketAnalyzer()
    trend = analyzer.analyze_trends(data)
    
    assert "BAIXA" in trend or "Bearish" in trend


@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_analyze_trends_empty_data():
    """Testa análise com dados vazios."""
    import pandas as pd
    
    data = pd.DataFrame()
    analyzer = MarketAnalyzer()
    trend = analyzer.analyze_trends(data)
    
    assert "insuficientes" in trend or "Empty" in trend


# ─────────────────────────────────────────────────────────────
#  Testes do EconomicSentinel Execute
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_execute_process_task(sentinel):
    """Testa execução de tarefa genérica."""
    task = {"action": "get_market_snapshot"}
    result = await sentinel._execute(task)
    
    assert isinstance(result, TaskResult)
    assert result.success is True


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_execute_cycle_generates_report(sentinel, tmp_path):
    """Testa que execute_cycle gera relatório JSON."""
    # Mock para evitar chamadas reais de API
    with patch.object(sentinel.engine, 'get_market_summary') as mock_summary, \
         patch.object(sentinel.engine, 'get_alpha_vantage_data') as mock_av_data, \
         patch.object(sentinel.analyzer, 'analyze_trends') as mock_trend:
        
        mock_summary.return_value = {"^GSPC": {"price": 4500, "change": 1.2}}
        mock_av_data.return_value = MagicMock(empty=False)
        mock_trend.return_value = "Tendência de ALTA"
        
        # Configura path temporário
        sentinel.report_path = str(tmp_path)
        
        await sentinel.execute_cycle()
        
        # Verifica que relatório foi criado
        report_files = list(tmp_path.glob("report_*.json"))
        assert len(report_files) > 0


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_execute_cycle_publishes_to_messagebus(sentinel_with_message_bus, tmp_path):
    """Testa que relatório é publicado na MessageBus."""
    sentinel = sentinel_with_message_bus
    
    with patch.object(sentinel.engine, 'get_market_summary') as mock_summary, \
         patch.object(sentinel.engine, 'get_alpha_vantage_data') as mock_av_data, \
         patch.object(sentinel.analyzer, 'analyze_trends') as mock_trend:
        
        mock_summary.return_value = {"^GSPC": {"price": 4500, "change": 1.2}}
        mock_av_data.return_value = MagicMock(empty=False)
        mock_trend.return_value = "Tendência de ALTA"
        
        sentinel.report_path = str(tmp_path)
        
        await sentinel.execute_cycle()
        
        # Verifica que publicou na MessageBus
        assert sentinel.message_bus.publish.called
        call_args = sentinel.message_bus.publish.call_args
        assert call_args[1]["topic"] == "economics.report_generated"


# ─────────────────────────────────────────────────────────────
#  Testes de Salvamento de Relatório
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_save_report(sentinel, tmp_path):
    """Testa salvamento de relatório JSON."""
    sentinel.report_path = str(tmp_path)
    
    report = {
        "timestamp": "2024-01-01T00:00:00",
        "market_summary": {"AAPL": {"price": 150}},
        "highlight": {"asset": "AAPL", "trend": "ALTA"},
    }
    
    sentinel.save_report(report)
    
    # Verifica que arquivo foi criado
    report_files = list(tmp_path.glob("report_*.json"))
    assert len(report_files) > 0
    
    # Verifica conteúdo
    with open(report_files[0], 'r') as f:
        saved_report = json.load(f)
    
    assert saved_report["timestamp"] == report["timestamp"]
    assert saved_report["market_summary"] == report["market_summary"]


@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_save_report_creates_directory():
    """Testa que diretório é criado se não existir."""
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    nested_path = os.path.join(temp_dir, "economics", "reports")
    
    try:
        sentinel = EconomicSentinel()
        sentinel.report_path = nested_path
        
        report = {"test": "data"}
        sentinel.save_report(report)
        
        assert os.path.exists(nested_path)
    finally:
        shutil.rmtree(temp_dir)


# ─────────────────────────────────────────────────────────────
#  Testes de Tratamento de Mensagens
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_handle_message_risk_adjustment(sentinel):
    """Testa handling de mensagem de ajuste de risco."""
    topic = "betting.request_risk_adjustment"
    payload = {"current_risk": 0.5, "target_risk": 0.3}
    
    # Não deve levantar exceção
    await sentinel.handle_message(topic, payload)


@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_handle_message_unknown_topic(sentinel):
    """Testa handling de mensagem com tópico desconhecido."""
    topic = "unknown.topic"
    payload = {"data": "test"}
    
    # Não deve levantar exceção
    await sentinel.handle_message(topic, payload)


# ─────────────────────────────────────────────────────────────
#  Testes de Comportamento com Dados Inválidos
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_market_summary_with_invalid_symbol():
    """Testa resumo de mercado com símbolo inválido."""
    with patch('yfinance.Ticker') as mock_ticker:
        mock_ticker.return_value.info = {}  # Info vazio
        
        engine = FinancialEngine(api_key="test_key")
        summary = await engine.get_market_summary(["INVALID"])
        
        assert "INVALID" in summary
        # Deve lidar graciosamente com dados faltantes


@pytest.mark.unit
@pytest.mark.economic_sentinel
def test_analyze_trends_with_partial_data():
    """Testa análise com dados parcialmente inválidos."""
    import pandas as pd
    
    # Cria dados com alguns valores NaN
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    data = pd.DataFrame({
        '4. close': [100 if i % 5 != 0 else None for i in range(30)]
    }, index=dates)
    
    analyzer = MarketAnalyzer()
    # Não deve crashar com dados parciais
    trend = analyzer.analyze_trends(data)
    assert isinstance(trend, str)


# ─────────────────────────────────────────────────────────────
#  Testes de Integração Leve
# ─────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.economic_sentinel
@pytest.mark.asyncio
async def test_full_cycle_mocked(sentinel_with_message_bus, tmp_path):
    """Testa ciclo completo com mocks."""
    sentinel = sentinel_with_message_bus
    sentinel.report_path = str(tmp_path)
    
    with patch.object(sentinel.engine, 'get_market_summary') as mock_summary, \
         patch.object(sentinel.engine, 'get_alpha_vantage_data') as mock_av_data, \
         patch.object(sentinel.analyzer, 'analyze_trends') as mock_trend:
        
        mock_summary.return_value = {
            "^GSPC": {"price": 4500, "change": 1.2, "currency": "USD"},
            "BTC-USD": {"price": 42000, "change": -2.5, "currency": "USD"},
        }
        
        import pandas as pd
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        mock_data = pd.DataFrame({
            '4. close': [100 + i * 0.5 for i in range(30)]
        }, index=dates)
        mock_av_data.return_value = mock_data
        mock_trend.return_value = "Tendência de ALTA"
        
        # Executa ciclo
        await sentinel.execute_cycle()
        
        # Verifica relatório criado
        report_files = list(tmp_path.glob("report_*.json"))
        assert len(report_files) > 0
        
        # Verifica publicação na MessageBus
        assert sentinel.message_bus.publish.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
