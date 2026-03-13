import logging
from typing import Dict, Any
from skills.skill_base import SkillBase
from core.verification.graph import CodeVerificationGraph
from core.verification.state import VerificationState

logger = logging.getLogger("moon.core.orchestrator")

class MoonOrchestrator:
    """
    Central orchestrator for The Moon ecosystem.
    Unifies skills and ensures code quality via the verification loop.
    """
    def __init__(self):
        self.skills: Dict[str, SkillBase] = {}
        self.verification_graph = CodeVerificationGraph()
        logger.info("MoonOrchestrator initialized.")

    def register_skill(self, skill: SkillBase):
        self.skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")

    async def execute_skill(self, skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if skill_name not in self.skills:
            return {"error": f"Skill {skill_name} not found"}
        
        logger.info(f"Executing skill: {skill_name}")
        return await self.skills[skill_name].execute(params)

    async def evaluate_solutions(self, task_description: str, context: Dict[str, Any]) -> str:
        """
        Tree of Thoughts (ToT) Implementation:
        Generates and evaluates multiple paths for complex tasks.
        """
        logger.info(f"Starting Tree of Thoughts evaluation for: {task_description[:50]}...")
        
        # Simulação da Proposição de Pensamentos
        thoughts = [
            {"id": 1, "plan": "Abordagem 1: Direta e Conservadora", "risk": "Baixo", "gain": "Médio"},
            {"id": 2, "plan": "Abordagem 2: Otimizada (High-Performance)", "risk": "Médio", "gain": "Alto"},
            {"id": 3, "plan": "Abordagem 3: Criativa/Experimental", "risk": "Alto", "gain": "Potencialmente Disruptivo"}
        ]
        
        # Lógica de Seleção (No futuro integrada a um modelo LLM específico para ToT)
        selected_thought = thoughts[1] # Selecionando o plano otimizado como padrão para o protótipo
        
        logger.info(f"ToT Selected Plan: {selected_thought['plan']}")
        return selected_thought["plan"]

    def verify_code(self, code: str, skill_context: str) -> Dict[str, Any]:
        """
        Runs the code through the verification loop.
        """
        state = VerificationState(
            original_command="Internal Verification",
            skill_name=skill_context,
            current_code=code
        )
        final_state = self.verification_graph.run(state)
        
        return {
            "status": final_state.status.value,
            "code": final_state.final_code,
            "score": final_state.quality_score,
            "errors": final_state.error_message
        }
