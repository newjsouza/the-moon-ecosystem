"""
core/security/__init__.py
Security layer for The Moon Ecosystem.

Implements:
- SecretManager: Validation and management of secrets
- InputValidator: CLI argument sanitization
- SecurityAuditLog: Append-only audit logging
- RateLimiter: Request rate limiting
- TelegramGuard: User authorization for Telegram bot
- AgentPermissions: Agent capability restrictions
"""

from core.security.secrets import SecretManager
from core.security.validator import InputValidator
from core.security.audit import SecurityAuditLog
from core.security.rate_limiter import RateLimiter
from core.security.guard import TelegramGuard, AgentPermissions

__all__ = [
    "SecretManager",
    "InputValidator",
    "SecurityAuditLog",
    "RateLimiter",
    "TelegramGuard",
    "AgentPermissions",
]
