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
        self.logger.info(f"KeyVault Bridge: Buscando APIs/Keys para: {task}")
        
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                if "discover" in task.lower():
                    # Triggers background discovery in KeyVault
                    response = await client.post("http://localhost:8080/api/keys/discover", json={"query": task})
                    return TaskResult(success=True, data=response.json())
                
                # Default behavior: list keys
                response = await client.get("http://localhost:8080/api/keys")
                keys = response.json()
                
                # Find best match for the task
                matches = [k for k in keys if k['name'].lower() in task.lower() or k.get('provider', '').lower() in task.lower()]
                
                return TaskResult(
                    success=True, 
                    data={
                        "matches": matches,
                        "total_vault_keys": len(keys)
                    }
                )
        except Exception as e:
            return TaskResult(success=False, error=f"KeyVault Bridge Error: {str(e)}")

