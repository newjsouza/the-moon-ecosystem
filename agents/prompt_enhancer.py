"""
agents/prompt_enhancer.py
Prompt Enhancer Agent - Intercepts commands and injects the MOON_CODEX directives.
"""
import os
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

class PromptEnhancerAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.CRITICAL # High priority as it's a middleware
        self.description = "Engenharia de Prompt Autônoma (Middleware Cognitivo)"
        self.logger = setup_logger("PromptEnhancerAgent")
        self.codex_path = "/home/johnathan/Área de trabalho/The Moon/MOON_CODEX.md"

    def _read_codex(self) -> str:
        """Reads the MOON_CODEX.md to inject into the prompt."""
        try:
            if os.path.exists(self.codex_path):
                with open(self.codex_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return "ALERTA: MOON_CODEX.md não encontrado."
        except Exception as e:
            self.logger.error(f"Erro ao ler Codex: {e}")
            return f"Erro ao ler Codex: {e}"

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        orchestrator = kwargs.get("orchestrator")
        if not orchestrator:
            return TaskResult(success=False, error="Orchestrator required for Enhancer.")

        self.logger.info(f"Interceptando e aprimorando o prompt original: '{task[:50]}...'")
        
        # 1. Read the Codex (System Brain)
        codex_content = self._read_codex()

        # 2. Build the Meta-Prompt
        enhancement_prompt = f"""
Você é o componente 'PromptEnhancerAgent' do The Moon.
Sua função é APERFEIÇOAR a INSTRUÇÃO ORIGINAL incorporando as diretrizes de nosso Codex, MAS PRESERVANDO RIGOROSAMENTE todas as restrições de formatação e estrutura da instrução original.

Aqui está o texto integral do nosso MOON_CODEX.md para seu contexto:

<MOON_CODEX>
{codex_content}
</MOON_CODEX>

INSTRUÇÃO ORIGINAL:
"{task}"

O QUE VOCÊ DEVE DEVOLVER:
Devolva ÚNICA E EXCLUSIVAMENTE o novo prompt aprimorado. 

REGRAS CRÍTICAS DE PRESERVAÇÃO E ENGENHARIA (METODOLOGIA QWEN3):
- **Plan-First:** Comando a IA executora a SEMPRE iniciar a resposta com uma seção `### Planejamento e Arquitetura`, descrevendo a lógica e os passos técnicos antes de escrever qualquer código.
- **Gratuidade (Diretriz 0.2):** Exija que qualquer biblioteca ou API sugerida seja estritamente 100% Gratuita e Open Source.
- Se a INSTRUÇÃO ORIGINAL continha exigências de formatação (YAML Frontmatter, "---", subtítulos, número de parágrafos ou contagem de palavras), VOCÊ DEVE MANTER ESSAS EXIGÊNCIAS EXATAS NO SEU PROMPT.
- Enobreça o vocabulário e a densidade técnica, garantindo que a IA resultante produza um texto vasto, explicativo e premium.
- Garanta que a IA executora resolva o problema de forma definitiva e sem placeholders.

"""
        # 3. Ask LLM to enhance the prompt
        self.logger.info("Solicitando refinamento ao LlmAgent...")
        llm_res = await orchestrator.execute(enhancement_prompt, agent_name="LlmAgent")
        
        if not llm_res.success:
            self.logger.error("Falha ao aprimorar prompt. Retornando o prompt original como fallback.")
            return TaskResult(success=True, data={"enhanced_prompt": task})
            
        enhanced_prompt = llm_res.data.get("response", task).strip()
        self.logger.info("Prompt aprimorado com sucesso incorporando o MOON_CODEX!")
        
        return TaskResult(success=True, data={"enhanced_prompt": enhanced_prompt})
