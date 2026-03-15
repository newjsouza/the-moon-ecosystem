"""
agents/betting_analyst.py
Betting Analyst Agent - Extração de Odds e Análise Probabilística.
"""
import asyncio
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

class BettingAnalystAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.LOW
        self.description = "Betting Analyst - Análise de Odds e Hedge Estratégico"
        self.logger = setup_logger("BettingAnalystAgent")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executa a coleta e análise de dados de apostas usando o SportsManager.
        """
        self.logger.info(f"Iniciando análise de mercado para: {task}")
        
        try:
            from skills.sports.manager import SportsManager
            manager = SportsManager()
            
            # Se for uma tarefa de monitoramento global
            if "monitor" in task.lower() or "loop" in task.lower():
                asyncio.create_task(manager.run_monitoring_loop())
                return TaskResult(success=True, data={"status": "Monitoring loop started in background."})
            
            # Se for uma análise de jogo específica (precisa de match_id em kwargs ou extraído de task)
            match_id = kwargs.get("match_id")
            if not match_id and "match" in task.lower():
                # Tenta extrair ID numérico do texto
                import re
                match = re.search(r'\d+', task)
                if match:
                    match_id = match.group()
            
            if match_id:
                result = await manager.analyze_match_live(match_id)
                return TaskResult(success=True, data=result)
            
            return TaskResult(
                success=False, 
                error="Nenhum Match ID fornecido para análise específica."
            )
            
        except ImportError:
            return TaskResult(success=False, error="SportsManager skill not found.")
        except Exception as e:
            self.logger.error(f"Erro na execução do BettingAnalyst: {e}")
            return TaskResult(success=False, error=str(e))
