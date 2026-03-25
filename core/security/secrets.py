"""
core/security/secrets.py
SecretManager — Singleton para validação e gestão de secrets.

Valida secrets críticos no boot e fornece interface segura para acesso.
"""
import os
import logging
from typing import Optional, Set

logger = logging.getLogger(__name__)


class SecretManager:
    """
    Singleton para gestão de secrets.
    
    Valida secrets críticos no boot e fornece acesso controlado.
    """
    
    _instance: Optional["SecretManager"] = None
    
    # Secrets críticos que DEVEM existir para boot seguro
    REQUIRED_SECRETS: Set[str] = {
        "GROQ_API_KEY",  # LLM provider
    }
    
    # Secrets opcionais (funcionalidades degradadas se ausentes)
    OPTIONAL_SECRETS: Set[str] = {
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_IDS",
        "YOUTUBE_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "HUGGINGFACE_TOKEN",
        "GITHUB_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    }
    
    def __new__(cls) -> "SecretManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        self._validated: bool = False
        self._missing_required: Set[str] = set()
        self._missing_optional: Set[str] = set()
        self._initialized = True
    
    def validate_boot(self) -> bool:
        """
        Valida todos os secrets críticos no boot.
        
        Returns:
            True se todos os secrets required estão presentes.
        """
        self._missing_required = set()
        self._missing_optional = set()
        
        for secret in self.REQUIRED_SECRETS:
            if not os.environ.get(secret):
                self._missing_required.add(secret)
        
        for secret in self.OPTIONAL_SECRETS:
            if not os.environ.get(secret):
                self._missing_optional.add(secret)
        
        self._validated = True
        
        if self._missing_required:
            logger.error(
                "BOOT: Missing required secrets — check .env. Missing: %s",
                self._missing_required
            )
            return False
        
        if self._missing_optional:
            logger.warning(
                "BOOT: Optional secrets missing (degraded mode): %s",
                self._missing_optional
            )
        
        logger.info("BOOT: All required secrets validated")
        return True
    
    def get_required(self, key: str) -> str:
        """
        Obtém um secret required, levantando erro se ausente.
        
        Args:
            key: Nome do secret.
            
        Returns:
            Valor do secret.
            
        Raises:
            ValueError: Se o secret não existe.
        """
        value = os.environ.get(key)
        if not value:
            raise ValueError(f"Required secret '{key}' is not set")
        return value
    
    def get_optional(self, key: str, default: str = "") -> str:
        """
        Obtém um secret optional, retornando default se ausente.
        
        Args:
            key: Nome do secret.
            default: Valor padrão se ausente.
            
        Returns:
            Valor do secret ou default.
        """
        return os.environ.get(key, default)
    
    def is_configured(self, key: str) -> bool:
        """Verifica se um secret está configurado."""
        return bool(os.environ.get(key))
    
    def get_missing_required(self) -> Set[str]:
        """Retorna conjunto de secrets required faltantes."""
        return self._missing_required.copy()
    
    def get_missing_optional(self) -> Set[str]:
        """Retorna conjunto de secrets optional faltantes."""
        return self._missing_optional.copy()
    
    def has_validated(self) -> bool:
        """Retorna se validação de boot já foi executada."""
        return self._validated
