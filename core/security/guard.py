"""
core/security/guard.py
TelegramGuard e AgentPermissions — Controle de acesso.

TelegramGuard: Autorização de usuários por ID (allowlist).
AgentPermissions: Restrições de capacidades por agente.
"""
import os
import logging
from typing import Dict, Optional, Set, List

from core.security.audit import SecurityAuditLog

logger = logging.getLogger(__name__)


class TelegramGuard:
    """
    Guard para Telegram bot.
    
    Autoriza apenas usuários cujos IDs estão na allowlist.
    """
    
    _instance: Optional["TelegramGuard"] = None
    
    def __new__(cls) -> "TelegramGuard":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._allowed_ids: Set[str] = set()
        self._audit = SecurityAuditLog()
        self._load_from_env()
        self._initialized = True
        
        logger.info("TelegramGuard iniciado: %d usuários allowlistados",
                    len(self._allowed_ids))
    
    def _load_from_env(self) -> None:
        """Carrega IDs permitidos do environment."""
        allowed_str = os.environ.get("TELEGRAM_ALLOWED_IDS", "")
        if allowed_str:
            # Suporta formato: "123456,789012" ou "123456, 789012"
            self._allowed_ids = {
                uid.strip()
                for uid in allowed_str.split(",")
                if uid.strip()
            }
        else:
            logger.warning(
                "TELEGRAM_ALLOWED_IDS não configurado — nenhum usuário autorizado!"
            )
    
    def is_allowed(self, user_id: str) -> bool:
        """
        Verifica se usuário está autorizado.
        
        Args:
            user_id: ID do usuário no Telegram.
            
        Returns:
            True se autorizado, False caso contrário.
        """
        user_id = str(user_id)
        allowed = user_id in self._allowed_ids
        
        if allowed:
            self._audit.log_auth_attempt(user_id, granted=True)
            logger.debug("Usuário %s autorizado", user_id)
        else:
            self._audit.log_auth_attempt(
                user_id,
                granted=False,
                reason="Not in allowlist",
            )
            logger.warning("Usuário %s NÃO autorizado (não está na allowlist)", user_id)
        
        return allowed
    
    def add_allowed(self, user_id: str) -> None:
        """Adiciona usuário à allowlist."""
        user_id = str(user_id)
        self._allowed_ids.add(user_id)
        self._audit.log_success("allowlist_add", "admin", resource=user_id)
        logger.info("Usuário %s adicionado à allowlist", user_id)
    
    def remove_allowed(self, user_id: str) -> None:
        """Remove usuário da allowlist."""
        user_id = str(user_id)
        self._allowed_ids.discard(user_id)
        self._audit.log_success("allowlist_remove", "admin", resource=user_id)
        logger.info("Usuário %s removido da allowlist", user_id)
    
    def get_allowed_ids(self) -> Set[str]:
        """Retorna cópia do conjunto de IDs permitidos."""
        return self._allowed_ids.copy()
    
    def reload_from_env(self) -> None:
        """Recarrega allowlist do environment."""
        self._allowed_ids.clear()
        self._load_from_env()
        logger.info("TelegramGuard recarregado do environment")


class AgentPermissions:
    """
    Controle de permissões por agente.
    
    Define quais recursos/capacidades cada agente pode usar.
    """
    
    # Permissões disponíveis
    PERMISSIONS = {
        "llm",              # Acesso a LLM (Groq, Gemini, etc.)
        "web_search",       # Pesquisa na web
        "file_read",        # Leitura de arquivos
        "file_write",       # Escrita de arquivos
        "command_exec",     # Execução de comandos shell
        "database",         # Acesso a banco de dados
        "api_external",     # Chamadas a APIs externas
        "telegram_send",    # Envio de mensagens Telegram
        "browser_control",  # Controle de navegador
        "youtube_access",   # Acesso ao YouTube
    }
    
    # Permissões default por tipo de agente
    DEFAULT_PERMISSIONS: Dict[str, Set[str]] = {
        "telegram_bot": {
            "llm", "telegram_send", "web_search", "file_read",
        },
        "deep_web_research": {
            "llm", "web_search", "api_external",
        },
        "data_pipeline": {
            "database", "file_read", "file_write",
        },
        "cli_agent": {
            "command_exec", "file_read", "file_write",
        },
        "browser_pilot": {
            "browser_control", "llm",
        },
        "apex_oracle": {
            "llm", "web_search", "api_external",
        },
        "default": {
            "llm", "file_read",
        },
    }
    
    def __init__(self) -> None:
        self._custom_perms: Dict[str, Set[str]] = {}
        self._audit = SecurityAuditLog()
        logger.info("AgentPermissions iniciado")
    
    def can_use(self, agent: str, permission: str) -> bool:
        """
        Verifica se agente tem permissão.
        
        Args:
            agent: Nome do agente.
            permission: Permissão a verificar.
            
        Returns:
            True se permitido.
        """
        if permission not in self.PERMISSIONS:
            logger.warning("Permissão desconhecida: %s", permission)
            return False
        
        perms = self._get_permissions(agent)
        allowed = permission in perms
        
        if not allowed:
            self._audit.log_failure(
                "permission_check",
                agent,
                resource=permission,
                reason="Not authorized",
            )
        
        return allowed
    
    def get_permissions(self, agent: str) -> Set[str]:
        """Retorna permissões de um agente."""
        return self._get_permissions(agent).copy()
    
    def _get_permissions(self, agent: str) -> Set[str]:
        """Obtém permissões para agente (custom ou default)."""
        if agent in self._custom_perms:
            return self._custom_perms[agent]
        
        # Tenta encontrar por tipo
        for agent_type, perms in self.DEFAULT_PERMISSIONS.items():
            if agent_type in agent.lower():
                return perms
        
        return self.DEFAULT_PERMISSIONS["default"]
    
    def set_permissions(self, agent: str, permissions: List[str]) -> None:
        """
        Define permissões customizadas para um agente.
        
        Args:
            agent: Nome do agente.
            permissions: Lista de permissões.
        """
        valid_perms = set()
        for p in permissions:
            if p in self.PERMISSIONS:
                valid_perms.add(p)
            else:
                logger.warning("Permissão inválida ignorada: %s", p)
        
        self._custom_perms[agent] = valid_perms
        self._audit.log_success(
            "permissions_set",
            "admin",
            resource=agent,
            metadata={"permissions": list(valid_perms)},
        )
        logger.info("Permissões customizadas definidas para %s: %s",
                    agent, valid_perms)
