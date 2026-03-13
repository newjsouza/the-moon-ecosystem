from .state import VerificationState

def route_after_syntax(state: VerificationState) -> str:
    if not state.syntax_ok:
        return "correct"
    return "next"

def route_after_standards(state: VerificationState) -> str:
    if not state.standards_ok:
        return "correct"
    return "next"

def route_after_security(state: VerificationState) -> str:
    if not state.security_ok:
        return "block"
    return "next"

def route_after_llm(state: VerificationState) -> str:
    if state.quality_score >= state.quality_threshold:
        return "done"
    elif state.current_iteration < state.max_iterations:
        return "iterate"
    else:
        return "fail"
