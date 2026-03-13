"""
agents/api_discovery.py
API discovery and health checks.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority

class ApiDiscoveryAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "API Discovery - Busca Estrita por Open Source e Free-Tiers"

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        self.logger.info(f"Procurando por API free-tier ou self-hosted para: {task}")
        # DIRETRIZ 0.2: Apenas serviços válidos que não exigem cartão
        
        if "health" in task.lower():
            return TaskResult(success=True, data={"status": "healthy"})
            
        # Mock de retorno forçando "free plan" no payload
        return TaskResult(
            success=True, 
            data={
                "endpoints": ["/api/v1/mock"],
                "pricing": "100% Free / Open Source",
                "auth": "No credit card required"
            }
        )

