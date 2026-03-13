from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

class VerificationStatus(Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    CORRECTING = "CORRECTING"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"

@dataclass
class VerificationState:
    """
    State object for the code verification loop.
    """
    original_command: str
    skill_name: str
    current_code: str = ""
    final_code: str = ""
    status: VerificationStatus = VerificationStatus.PENDING
    error_message: Optional[str] = None
    quality_score: float = 0.0
    current_iteration: int = 0
    max_iterations: int = 3
    quality_threshold: float = 0.85
    
    # Validation flags
    syntax_ok: bool = False
    standards_ok: bool = False
    security_ok: bool = False
    
    # History of iterations
    history: List[Dict[str, Any]] = field(default_factory=list)

    def save_iteration(self, duration_ms: float):
        code_snip = str(self.current_code)[:200] + "..." if self.current_code else "None"
        self.history.append({
            "iteration": self.current_iteration,
            "code_snippet": code_snip,
            "score": self.quality_score,
            "status": self.status.value,
            "duration": duration_ms
        })
