"""
agents/blog/manager.py
Blog Manager Agent - Orchestrator of the Blog Ecosystem.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

class BlogManagerAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.CRITICAL
        self.description = "Blog Manager General - Orquestra BlogWriter e BlogPublisher"
        self.logger = setup_logger("BlogManagerAgent")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        orchestrator = kwargs.get("orchestrator")
        if not orchestrator:
            return TaskResult(success=False, error="O BlogManager precisa do orchestrator via kwargs.")
            
        self.logger.info(f"== INICIANDO FLUXO DE BLOG AUTÔNOMO: {task} ==")
        
        # 1. Planejamento Geral (opcional via ArchitectAgent)
        self.logger.info("Solicitando planejamento ao ArchitectAgent...")
        plan_res = await orchestrator.execute(f"Pauta para blog post sobre {task}", agent_name="ArchitectAgent")
        self.logger.info(f"Plano recebido: {plan_res.success}")

        # 2. Pesquisa e Geração
        self.logger.info("Delegando pesquisa e redação ao BlogWriterAgent...")
        write_res = await orchestrator.execute(task, agent_name="BlogWriterAgent", orchestrator=orchestrator)
        if not write_res.success or not write_res.data:
             self.logger.error(f"Falha na redação: {write_res.error}")
             return TaskResult(success=False, error=write_res.error or "Dados de redação ausentes")
        
        markdown_content = write_res.data.get("markdown")
        
        # 3. Publicação (Usa recursos do Terminal)
        self.logger.info("Delegando deploy automático ao BlogPublisherAgent...")
        pub_res = await orchestrator.execute(task, agent_name="BlogPublisherAgent", orchestrator=orchestrator, markdown=markdown_content)
        if not pub_res.success:
            self.logger.error(f"Falha ao publicar via terminal: {pub_res.error}")
            return TaskResult(success=False, error=pub_res.error)

        return TaskResult(success=True, data={"blog_url": pub_res.data.get("url"), "status": "Totalmente publicado e operante."})
