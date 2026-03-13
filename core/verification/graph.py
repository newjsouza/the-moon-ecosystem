import time
import logging
from .state import VerificationState, VerificationStatus
from .nodes import (
    node_syntax_validator,
    node_standards_checker,
    node_security_scanner,
    node_llm_reviewer
)
from .router import (
    route_after_syntax,
    route_after_standards,
    route_after_security,
    route_after_llm
)

logger = logging.getLogger("moon.verification.graph")

class CodeVerificationGraph:
    """
    Orchestrates the code verification loop.
    Iterates through nodes until code is approved or fails.
    """
    def run(self, state: VerificationState) -> VerificationState:
        logger.info(f"[GRAPH] Starting verification for {state.skill_name}")
        
        while state.status not in [VerificationStatus.APPROVED, VerificationStatus.BLOCKED, VerificationStatus.FAILED]:
            start_time = time.time()
            state.current_iteration += 1
            
            # 1. Syntax check
            state = node_syntax_validator(state)
            if route_after_syntax(state) == "correct":
                state.status = VerificationStatus.CORRECTING
                # In a real scenario, we'd call an LLM to fix the syntax here
                if state.current_iteration >= state.max_iterations:
                    state.status = VerificationStatus.FAILED
                state.save_iteration((time.time() - start_time) * 1000)
                continue

            # 2. Standards check
            state = node_standards_checker(state)
            if route_after_standards(state) == "correct":
                state.status = VerificationStatus.CORRECTING
                if state.current_iteration >= state.max_iterations:
                    state.status = VerificationStatus.FAILED
                state.save_iteration((time.time() - start_time) * 1000)
                continue

            # 3. Security check
            state = node_security_scanner(state)
            if route_after_security(state) == "block":
                state.status = VerificationStatus.BLOCKED
                state.save_iteration((time.time() - start_time) * 1000)
                break

            # 4. LLM Review
            state = node_llm_reviewer(state)
            next_move = route_after_llm(state)
            
            if next_move == "done":
                state.status = VerificationStatus.APPROVED
                state.final_code = state.current_code
            elif next_move == "iterate":
                state.status = VerificationStatus.CORRECTING
            else:
                state.status = VerificationStatus.FAILED
            
            state.save_iteration((time.time() - start_time) * 1000)
            
            if state.current_iteration >= state.max_iterations and state.status != VerificationStatus.APPROVED:
                state.status = VerificationStatus.FAILED
                break
                
        if state.status == VerificationStatus.APPROVED and state.current_iteration > 0:
            self._document_learning(state)

        logger.info(f"[GRAPH] Verification finished with status: {state.status.value}")
        return state

    def _document_learning(self, state: VerificationState):
        """
        Self-Healing / Learning:
        Records successful corrections to the system memory (MOON_CODEX.md).
        """
        logger.info(f"[LEARNING] Recording correction for skill: {state.skill_name}")
        # Lógica para atualizar o Codex em background (simulada via log por enquanto)
        # No futuro, usará o auto_edit.py conforme Diretriz 0.4
