"""
agents/blog/direct_writer.py
Special agent to generate dense content bypassing the enhancer for high-precision tasks.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

class DirectWriterAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.CRITICAL
        self.description = "Gerador de Conteúdo Denso Direto (Bypass Enhancer)"
        self.logger = setup_logger("DirectWriterAgent")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        orchestrator = kwargs.get("orchestrator")
        if not orchestrator:
            return TaskResult(success=False, error="Orchestrator required for DirectWriter")
            
        context = kwargs.get("context", "Sem contexto adicional.")
        
        prompt = f'''
        Você é um escritor sênior de tecnologia. Gere um artigo de blog sobre: "{task}"
        Use estas REGRAS RÍGIDAS:
        1. Gere MÍNIMO 6 parágrafos longos (150+ palavras cada).
        2. Seja profundo e explicativo.
        3. Formate com YAML Frontmatter:
        ---
        title: "{task}"
        date: "2026-03-12"
        author: "The Moon AI"
        category: "Deep Tech"
        image: "capa.jpg"
        excerpt: "Impacto da {task} na década atual."
        ---
        Artigo contextualizado: {context}
        '''
        llm_res = await orchestrator.execute(prompt, agent_name="LlmAgent")
        return llm_res
