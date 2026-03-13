"""
agents/youtube_manager.py
Youtube Manager Agent - Estratégia, Roteirização e SEO de Vídeos.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

class YoutubeManagerAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.MEDIUM
        self.description = "YouTube Manager - Roteirização e Estratégia de Conteúdo"
        self.logger = setup_logger("YoutubeManagerAgent")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executa a lógica de roteirização e planejamento de SEO para YouTube.
        """
        orchestrator = kwargs.get("orchestrator")
        self.logger.info(f"Iniciando planejamento de vídeo para: {task}")
        
        # O esqueleto inicial foca em delegar a roteirização ao LlmAgent
        # usando a metodologia Plan-First via PromptEnhancer.
        
        prompt = f'''
        Você é um especialista em YouTube e retenção de público. 
        Crie um roteiro de vídeo de 10 minutos para o tema: {task}.
        
        O roteiro deve conter:
        1. Gancho (Hook) inicial de 30 segundos.
        2. Estrutura de tópicos principais.
        3. Chamada para ação (CTA).
        4. Sugestões de Título (clickbait ético) e Tags de SEO.
        '''
        
        if orchestrator:
            # Tenta usar o Enhancer para garantir conformidade com o Codex
            enhancement_res = await orchestrator.execute(prompt, agent_name="PromptEnhancerAgent")
            final_prompt = enhancement_res.data.get("enhanced_prompt", prompt) if enhancement_res.success else prompt
            
            # Execução via LlmAgent (com rodízio automático)
            llm_res = await orchestrator.execute(final_prompt, agent_name="LlmAgent")
            
            if llm_res.success:
                return TaskResult(
                    success=True, 
                    data={"script": llm_res.data.get("response"), "topic": task}
                )
        
        return TaskResult(success=False, error="Falha na orquestração ou geração do roteiro.")
