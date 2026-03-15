import asyncio
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd
import yfinance as yf
from alpha_vantage.timeseries import TimeSeries

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus

# Configuração de Logging
logger = logging.getLogger("EconomicSentinel")

class FinancialEngine:
    """Motor de coleta de dados financeiros utilizando Alpha Vantage e yfinance."""
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ts = TimeSeries(key=api_key, output_format='pandas')

    async def get_market_summary(self, symbols: List[str]) -> Dict[str, Any]:
        """Obtém um resumo do mercado para os símbolos fornecidos."""
        summary = {}
        for symbol in symbols:
            try:
                # Usando yfinance para dados rápidos
                ticker = yf.Ticker(symbol)
                info = ticker.info
                summary[symbol] = {
                    "price": info.get("regularMarketPrice") or info.get("currentPrice"),
                    "change": info.get("regularMarketChangePercent") or 0.0,
                    "currency": info.get("currency", "USD")
                }
            except Exception as e:
                logger.error(f"Erro ao obter dados para {symbol}: {e}")
                summary[symbol] = {"error": str(e)}
        return summary

    async def get_alpha_vantage_data(self, symbol: str) -> pd.DataFrame:
        """Obtém dados históricos detalhados da Alpha Vantage."""
        try:
            data, meta_data = self.ts.get_daily(symbol=symbol, outputsize='compact')
            return data
        except Exception as e:
            logger.error(f"Erro Alpha Vantage para {symbol}: {e}")
            return pd.DataFrame()

class MarketAnalyzer:
    """Analisador de tendências e sentimentos de mercado."""
    def analyze_trends(self, data: pd.DataFrame) -> str:
        if data.empty:
            return "Dados insuficientes para análise."
        
        # Lógica simplificada de tendência (SMA)
        close_prices = data['4. close']
        sma_20 = close_prices.rolling(window=20).mean().iloc[-1]
        current_price = close_prices.iloc[-1]
        
        if current_price > sma_20:
            return "Tendência de ALTA (Bullish)"
        elif current_price < sma_20:
            return "Tendência de BAIXA (Bearish)"
        else:
            return "Tendência NEUTRA"

class EconomicSentinel(AgentBase):
    """
    Agente sentinela focado em inteligência econômica e financeira.
    Monitora mercados, gera relatórios e integra insights ao ecossistema.
    """
    def __init__(self):
        super().__init__()
        self.name = "EconomicSentinel"
        self.priority = AgentPriority.MEDIUM
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")
        self.engine = FinancialEngine(self.api_key)
        self.analyzer = MarketAnalyzer()
        self.report_path = "data/economics/reports/"

    async def initialize(self) -> bool:
        logger.info(f"{self.name} inicializado.")
        os.makedirs(self.report_path, exist_ok=True)
        return True

    async def start(self):
        logger.info(f"{self.name} iniciado e monitorando...")
        # Loop principal (exemplo: a cada 1 hora)
        while True:
            await self.execute_cycle()
            await asyncio.sleep(3600)

    async def _execute(self, task: Dict[str, Any]) -> TaskResult:
        """Implementação do método abstrato de AgentBase."""
        logger.info(f"Executando tarefa no {self.name}: {task.get('action')}")
        return await self.process_task(task)

    async def execute_cycle(self):
        """Executa um ciclo completo de monitoramento e relatório."""
        logger.info("Iniciando ciclo de análise econômica...")
        symbols = ["^GSPC", "BTC-USD", "EURUSD=X"] # S&P 500, Bitcoin, EUR/USD
        
        summary = await self.engine.get_market_summary(symbols)
        
        # Análise baseada em dados da Alpha Vantage (exemplo com Apple)
        av_data = await self.engine.get_alpha_vantage_data("AAPL")
        trend = self.analyzer.analyze_trends(av_data)
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "market_summary": summary,
            "highlight": {
                "asset": "AAPL",
                "trend": trend
            }
        }
        
        self.save_report(report)
        
        # Notifica o ecossistema via MessageBus
        if hasattr(self, 'message_bus') and self.message_bus:
            await self.message_bus.publish(
                sender=self.name,
                topic="economics.report_generated",
                payload=report
            )

    def save_report(self, report: Dict[str, Any]):
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(self.report_path, filename)
        with open(path, "w") as f:
            json.dump(report, f, indent=4)
        logger.info(f"Relatório salvo em: {path}")

    async def handle_message(self, topic: str, payload: Any):
        """Lida com mensagens recebidas no MessageBus."""
        if topic == "betting.request_risk_adjustment":
            logger.info("Recebido pedido de ajuste de risco financeiro.")
            # Aqui poderia haver uma lógica de cálculo baseada na volatilidade do mercado
            pass

    async def process_task(self, task: Dict[str, Any]) -> TaskResult:
        """Processa tarefas específicas enviadas pelo Orquestrador."""
        # Exemplo: "get_market_snapshot"
        return TaskResult(success=True, data={"status": "Online"})
