"""
core/security/validator.py
InputValidator — Validação e sanitização de inputs.

Protege contra:
- Injeção de comandos shell
- Path traversal
- Argumentos maliciosos
"""
import os
import re
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class InputValidator:
    """
    Validador de inputs do usuário.
    
    Sanitiza argumentos CLI e previne injeção de comandos.
    """
    
    # Caracteres perigosos para shell
    DANGEROUS_CHARS = re.compile(r'[;&|`$(){}!\[\]<>\\]')
    
    # Patterns de ataques conhecidos
    ATTACK_PATTERNS = [
        r'\.\./',           # Path traversal
        r'\.\.\\',          # Path traversal Windows
        r'/etc/passwd',     # Leitura de arquivos sistema
        r'/etc/shadow',     # Leitura de shadows
        r'rm\s+(-[rf]+\s+)?/',  # rm recursivo na raiz
        r'dd\s+if=',        # dd attack
        r':\(\)\s*\{',      # Shellshock
        r'\$\{',            # Expansão de variável
        r'`[^`]+`',         # Command substitution
        r'\$\([^)]+\)',     # Command substitution $()
    ]
    
    # Whitelist de comandos seguros (para CLI harness)
    SAFE_COMMANDS = {
        'ls', 'dir', 'cat', 'head', 'tail', 'wc', 'grep', 'egrep',
        'find', 'sort', 'uniq', 'cut', 'tr', 'sed', 'awk',
        'python', 'python3', 'node', 'npm', 'pip', 'pip3',
        'git', 'docker', 'docker-compose',
        'echo', 'printf', 'date', 'time', 'whoami', 'pwd',
        'mkdir', 'cp', 'mv', 'touch', 'chmod', 'chown',
        'ps', 'top', 'htop', 'df', 'du', 'free',
        'curl', 'wget', 'ping', 'netstat', 'ss',
        'systemctl', 'journalctl',
        'apt', 'apt-get', 'yum', 'dnf', 'pacman',
    }
    
    @classmethod
    def validate_cli_arg(cls, arg: str) -> Tuple[bool, str]:
        """
        Valida um argumento de linha de comando.
        
        Args:
            arg: Argumento a validar.
            
        Returns:
            Tuple (is_valid, reason).
        """
        if not arg:
            return False, "Argumento vazio"
        
        # Check caracteres perigosos
        if cls.DANGEROUS_CHARS.search(arg):
            return False, f"Caracteres perigosos detectados: {arg}"
        
        # Check patterns de ataque
        for pattern in cls.ATTACK_PATTERNS:
            if re.search(pattern, arg, re.IGNORECASE):
                return False, f"Pattern de ataque detectado: {pattern}"
        
        # Check tamanho máximo
        if len(arg) > 4096:
            return False, "Argumento muito longo (>4096 chars)"
        
        return True, "OK"
    
    @classmethod
    def safe_cli_args(cls, args: List[str]) -> List[str]:
        """
        Filtra uma lista de argumentos, removendo os perigosos.
        
        Args:
            args: Lista de argumentos.
            
        Returns:
            Lista apenas com argumentos seguros.
            
        Raises:
            ValueError: Se algum argumento é perigoso.
        """
        safe = []
        for arg in args:
            is_valid, reason = cls.validate_cli_arg(arg)
            if not is_valid:
                logger.warning("Argumento bloqueado: %s (%s)", arg, reason)
                raise ValueError(f"Unsafe argument: {reason}")
            safe.append(arg)
        return safe
    
    @classmethod
    def validate_command(cls, command: str) -> Tuple[bool, str]:
        """
        Valida um comando (primeira palavra do args).
        
        Args:
            command: Comando a validar.
            
        Returns:
            Tuple (is_allowed, reason).
        """
        # Extrai nome do comando (primeira palavra)
        cmd_name = command.split()[0].lower() if command else ""
        
        # Remove path se presente
        cmd_name = os.path.basename(cmd_name)
        
        if cmd_name not in cls.SAFE_COMMANDS:
            return False, f"Comando não permitido: {cmd_name}"
        
        return True, "OK"
    
    @classmethod
    def sanitize_path(cls, path: str, base_dir: Optional[str] = None) -> str:
        """
        Sanitiza um path, prevenindo path traversal.
        
        Args:
            path: Path a sanitizar.
            base_dir: Diretório base para resolução (default: cwd).
            
        Returns:
            Path absoluto e normalizado.
            
        Raises:
            ValueError: Se o path tenta escapar do base_dir.
        """
        # Resolve path absoluto
        if base_dir:
            full_path = os.path.abspath(os.path.join(base_dir, path))
        else:
            full_path = os.path.abspath(path)
        
        # Verifica se está dentro do base_dir
        if base_dir:
            base_abs = os.path.abspath(base_dir)
            if not full_path.startswith(base_abs):
                raise ValueError(f"Path traversal detectado: {path}")
        
        return full_path
    
    @classmethod
    def validate_user_input(cls, text: str, max_length: int = 4096) -> Tuple[bool, str]:
        """
        Valida input de usuário (para LLM prompts).

        Args:
            text: Texto do usuário.
            max_length: Tamanho máximo permitido.

        Returns:
            Tuple (is_valid, reason).
        """
        if not text:
            return False, "Input vazio"

        if len(text) > max_length:
            return False, f"Input muito longo (>{max_length} chars)"

        # Check para tentativas óbvias de injection
        dangerous = ['<script>', '```', '"""', "'''"]
        for d in dangerous:
            if d.lower() in text.lower():
                return False, f"Conteúdo potencialmente malicioso: {d}"

        return True, "OK"

    # Internal agents: known agent naming patterns
    # Any actor NOT matching these patterns is treated as external (stricter limits)
    _INTERNAL_AGENT_PATTERNS = (
        "_agent",  # architect_agent, blog_agent, etc.
        "agent_",  # agent_name pattern
    )
    _USER_MAX_LENGTH = 4_096
    _AGENT_MAX_LENGTH = 32_000

    @classmethod
    def _is_internal_agent(cls, actor: str) -> bool:
        """Check if actor is an internal agent based on naming pattern."""
        actor_lower = actor.lower()
        return any(pattern in actor_lower for pattern in cls._INTERNAL_AGENT_PATTERNS)

    @classmethod
    def validate_llm_prompt(cls, text: str, actor: str = "unknown") -> Tuple[bool, str]:
        """
        Valida prompts de LLM com limite diferenciado por tipo de actor.

        Actors externos (user, telegram, api, unknown, test_user, etc.) → 4096 chars + XSS check
        Agents internos (*_agent ou agent_*) → 32000 chars, sem restrição de backticks/code blocks

        Args:
            text: Texto do prompt.
            actor: Identificador do actor ("user", "telegram", "agent_name", etc.)

        Returns:
            Tuple (is_valid, reason).
        """
        if not text:
            return False, "Empty prompt"

        is_internal = cls._is_internal_agent(actor)
        max_length = cls._AGENT_MAX_LENGTH if is_internal else cls._USER_MAX_LENGTH

        if len(text) > max_length:
            return False, f"Prompt too long (>{max_length} chars, actor={actor})"

        # Injection check ONLY for external/user actors
        # Internal agents legitimately use ```, """, ''' in code and RAG context
        if not is_internal:
            dangerous_external = ["<script>", "javascript:", "data:text/html"]
            for pattern in dangerous_external:
                if pattern.lower() in text.lower():
                    return False, f"Potentially malicious content detected: {pattern}"

        return True, "OK"
