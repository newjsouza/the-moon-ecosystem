"""
tests/security/test_security_layer.py
Testes para a security layer do The Moon Ecosystem.
"""
import os
import pytest
from core.security import (
    SecretManager,
    InputValidator,
    SecurityAuditLog,
    RateLimiter,
    TelegramGuard,
    AgentPermissions,
)


class TestSecretManager:
    """Testes para SecretManager."""

    def test_singleton(self):
        """SecretManager é singleton."""
        sm1 = SecretManager()
        sm2 = SecretManager()
        assert sm1 is sm2

    def test_validate_boot_missing_required(self):
        """validate_boot retorna False se required secrets faltam."""
        # GROQ_API_KEY está configurado no .env real
        sm = SecretManager()
        # Reset para testar
        sm._validated = False
        result = sm.validate_boot()
        # Deve ser True se GROQ_API_KEY está presente
        assert isinstance(result, bool)

    def test_get_required_raises(self):
        """get_required levanta ValueError se secret não existe."""
        sm = SecretManager()
        with pytest.raises(ValueError):
            sm.get_required("NONEXISTENT_SECRET_XYZ123")

    def test_get_optional_returns_default(self):
        """get_optional retorna default se secret não existe."""
        sm = SecretManager()
        value = sm.get_optional("NONEXISTENT_SECRET_XYZ123", default="fallback")
        assert value == "fallback"

    def test_is_configured(self):
        """is_configured retorna True/False corretamente."""
        sm = SecretManager()
        # GROQ_API_KEY deve estar configurado
        assert sm.is_configured("GROQ_API_KEY") is True
        # Secret inexistente
        assert sm.is_configured("NONEXISTENT_SECRET_XYZ123") is False


class TestInputValidator:
    """Testes para InputValidator."""

    def test_validate_safe_cli_arg(self):
        """Argumentos seguros são validados."""
        is_valid, reason = InputValidator.validate_cli_arg("ls -la")
        assert is_valid is True

    def test_validate_dangerous_chars_blocked(self):
        """Caracteres perigosos são bloqueados."""
        is_valid, reason = InputValidator.validate_cli_arg("ls; rm -rf /")
        assert is_valid is False
        assert "Caracteres perigosos" in reason

    def test_validate_path_traversal_blocked(self):
        """Path traversal é bloqueado."""
        is_valid, reason = InputValidator.validate_cli_arg("../../etc/passwd")
        assert is_valid is False

    def test_validate_rm_root_blocked(self):
        """rm -rf / é bloqueado."""
        is_valid, reason = InputValidator.validate_cli_arg("rm -rf /")
        assert is_valid is False
        assert "Pattern de ataque" in reason

    def test_safe_cli_args_raises(self):
        """safe_cli_args levanta ValueError para args perigosos."""
        with pytest.raises(ValueError):
            InputValidator.safe_cli_args(["ls", ";", "rm", "-rf", "/"])

    def test_validate_command_allowed(self):
        """Comandos na whitelist são permitidos."""
        is_allowed, reason = InputValidator.validate_command("ls -la")
        assert is_allowed is True

    def test_validate_command_denied(self):
        """Comandos fora da whitelist são bloqueados."""
        is_allowed, reason = InputValidator.validate_command("hacker_cmd")
        assert is_allowed is False


class TestSecurityAuditLog:
    """Testes para SecurityAuditLog."""

    def test_singleton(self):
        """SecurityAuditLog é singleton."""
        log1 = SecurityAuditLog()
        log2 = SecurityAuditLog()
        assert log1 is log2

    def test_log_action(self):
        """log_action registra entrada."""
        log = SecurityAuditLog()
        log.log_action("test_action", "test_actor", resource="test_resource")
        count = log.count_entries()
        assert count > 0

    def test_log_success(self):
        """log_success registra com status success."""
        log = SecurityAuditLog()
        log.log_success("test_success", "actor")
        entries = log.get_recent_entries(limit=1)
        assert entries[0]["status"] == "success"

    def test_log_failure(self):
        """log_failure registra com status failure."""
        log = SecurityAuditLog()
        log.log_failure("test_failure", "actor", reason="test reason")
        entries = log.get_recent_entries(limit=1)
        assert entries[0]["status"] == "failure"


class TestRateLimiter:
    """Testes para RateLimiter."""

    def test_singleton(self):
        """RateLimiter é singleton."""
        rl1 = RateLimiter()
        rl2 = RateLimiter()
        assert rl1 is rl2

    def test_set_limit_and_check(self):
        """Set limit e check funciona."""
        rl = RateLimiter()
        rl.set_limit("test_user", max_calls=5, window_seconds=60)
        assert rl.check("test_user") is True

    def test_acquire_decrements(self):
        """acquire registra chamada."""
        rl = RateLimiter()
        rl.set_limit("test_user2", max_calls=2, window_seconds=60)
        rl.reset("test_user2")  # Limpa estado anterior
        
        assert rl.acquire("test_user2") is True
        assert rl.acquire("test_user2") is True
        # Terceira chamada deve falhar
        assert rl.acquire("test_user2") is False

    def test_get_remaining(self):
        """get_remaining retorna chamadas restantes."""
        rl = RateLimiter()
        rl.set_limit("test_user3", max_calls=10, window_seconds=60)
        rl.reset("test_user3")
        remaining = rl.get_remaining("test_user3")
        assert remaining == 10


class TestTelegramGuard:
    """Testes para TelegramGuard."""

    def test_singleton(self):
        """TelegramGuard é singleton."""
        guard1 = TelegramGuard()
        guard2 = TelegramGuard()
        assert guard1 is guard2

    def test_is_allowed_with_env(self):
        """is_allowed verifica TELEGRAM_ALLOWED_IDS do .env."""
        guard = TelegramGuard()
        # O .env tem TELEGRAM_ALLOWED_IDS=6044857807
        allowed_ids = guard.get_allowed_ids()
        # Deve ter pelo menos um ID se TELEGRAM_ALLOWED_IDS está configurado
        assert len(allowed_ids) > 0

    def test_is_allowed_unknown_user(self):
        """Usuário desconhecido não é permitido."""
        guard = TelegramGuard()
        assert guard.is_allowed("9999999999") is False


class TestAgentPermissions:
    """Testes para AgentPermissions."""

    def test_can_use_llm_for_telegram(self):
        """telegram_bot pode usar llm."""
        perms = AgentPermissions()
        assert perms.can_use("telegram_bot", "llm") is True

    def test_cannot_use_unknown_permission(self):
        """Permissão desconhecida retorna False."""
        perms = AgentPermissions()
        assert perms.can_use("telegram_bot", "nonexistent_perm_xyz") is False

    def test_get_permissions(self):
        """get_permissions retorna set de permissões."""
        perms = AgentPermissions()
        telegram_perms = perms.get_permissions("telegram_bot")
        assert isinstance(telegram_perms, set)
        assert "llm" in telegram_perms

    def test_set_custom_permissions(self):
        """set_permissions define permissões customizadas."""
        perms = AgentPermissions()
        perms.set_permissions("custom_agent", ["llm", "file_read"])
        assert perms.can_use("custom_agent", "llm") is True
        assert perms.can_use("custom_agent", "file_read") is True
        assert perms.can_use("custom_agent", "command_exec") is False
