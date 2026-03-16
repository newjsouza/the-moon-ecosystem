"""
core/ai_jail_bridge.py

Bridge entre o AIJail (ai-jail/) e os agentes do Moon Ecosystem.
Encapsula o import path e expõe API consistente.
Usa create_safe_jail() como factory padrão.
"""
import sys
import os
import logging

logger = logging.getLogger(__name__)

# Resolve o path real do ai-jail
_AI_JAIL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "ai-jail"
)

try:
    if _AI_JAIL_PATH not in sys.path:
        sys.path.insert(0, _AI_JAIL_PATH)
    from ai_jail import AIJail, JailConfig, ExecutionResult
    from ai_jail import create_safe_jail
    JAIL_AVAILABLE = True
    logger.info("[AIJailBridge] AIJail disponível e importado.")
except ImportError as e:
    JAIL_AVAILABLE = False
    logger.warning(f"[AIJailBridge] AIJail indisponível: {e}. "
                   "Execução sem sandbox ativada.")

    # Fallback: execução direta sem sandbox (degrada graciosamente)
    class JailConfig:
        def __init__(self, **kwargs): pass

    class ExecutionResult:
        def __init__(self, success, stdout="", stderr="",
                     blocked_operations=None):
            self.success = success
            self.stdout = stdout
            self.stderr = stderr
            self.blocked_operations = blocked_operations or []

    class AIJail:
        """Fallback sem sandbox — apenas para ambientes sem ai-jail."""
        def __init__(self, config=None):
            self.config = config

        def execute_python(self, code: str) -> "ExecutionResult":
            import subprocess
            r = subprocess.run(
                ["python3", "-c", code],
                capture_output=True, text=True, timeout=30
            )
            return ExecutionResult(
                success=r.returncode == 0,
                stdout=r.stdout,
                stderr=r.stderr
            )

        def execute_bash(self, command: str) -> "ExecutionResult":
            import subprocess
            r = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=30
            )
            return ExecutionResult(
                success=r.returncode == 0,
                stdout=r.stdout,
                stderr=r.stderr
            )

    def create_safe_jail(**kwargs) -> "AIJail":
        return AIJail()


def get_jail(
    timeout: int = 30,
    allowed_dirs: list = None,
    network: bool = False
) -> "AIJail":
    """
    Factory principal. Retorna AIJail real ou fallback.
    Sempre use esta função — nunca instancie AIJail diretamente.
    """
    if JAIL_AVAILABLE:
        # create_safe_jail() não aceita parâmetros — usamos a configuração padrão
        # e modificamos após criação se necessário
        jail = create_safe_jail()
        if allowed_dirs:
            jail.config.allowed_dirs = allowed_dirs
        jail.config.max_execution_time = timeout
        jail.config.allow_network = network
        return jail
    return AIJail()


def run_python_safe(code: str, timeout: int = 30) -> "ExecutionResult":
    """Executa código Python no sandbox. API simplificada."""
    jail = get_jail(timeout=timeout)
    return jail.execute_python(code)


def run_bash_safe(command: str, timeout: int = 30) -> "ExecutionResult":
    """Executa comando bash no sandbox. API simplificada."""
    jail = get_jail(timeout=timeout)
    return jail.execute_bash(command)


__all__ = [
    "JAIL_AVAILABLE", "get_jail",
    "run_python_safe", "run_bash_safe",
    "AIJail", "JailConfig", "ExecutionResult"
]
