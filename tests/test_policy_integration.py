"""tests/test_policy_integration.py — Testes de integração de política com fluxo real"""

from unittest.mock import AsyncMock, Mock
from core.policy_engine import PolicyRule
from core.orchestrator import Orchestrator


class TestPolicyIntegration:
    def test_owner_can_do_everything(self):
        """Testa se user=johnathan, qualquer comando → allowed."""
        orch = Orchestrator()
        
        # Add the owner rule
        owner_rule = PolicyRule(
            rule_id="allow-owner-all",
            description="Johnathan tem acesso total a tudo",
            effect="allow",
            channels=["*"],
            users=["johnathan", "owner"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=100
        )
        orch.policy_engine.add_rule(owner_rule)
        
        # Test various commands with johnathan user
        commands_to_test = ["/flow-new", "/flow-retry", "/apex", "/status", "/admin"]
        for cmd in commands_to_test:
            allowed, reason = orch._check_policy(cmd, user_id="johnathan")
            assert allowed is True, f"Command {cmd} should be allowed for johnathan"

    def test_telegram_cannot_flow_retry(self):
        """Testa se channel=telegram, /flow-retry → denied."""
        orch = Orchestrator()
        
        # Add the deny rule for telegram admin commands
        deny_rule = PolicyRule(
            rule_id="deny-telegram-admin",
            description="Telegram não pode executar comandos administrativos de flow",
            effect="deny",
            channels=["telegram"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["/flow-retry", "/flow-resume", "/flow-new"],
            priority=60
        )
        orch.policy_engine.add_rule(deny_rule)
        
        # Test flow-retry command with telegram
        allowed, reason = orch._check_policy("/flow-retry", channel_type="telegram", user_id="any_user")
        assert allowed is False, "Command /flow-retry should be denied for telegram channel"

    def test_telegram_can_apex(self):
        """Testa se channel=telegram, /apex → allowed."""
        orch = Orchestrator()
        
        # Add the allow rule for safe commands on telegram
        allow_rule = PolicyRule(
            rule_id="allow-telegram-safe-commands",
            description="Telegram pode usar comandos de consulta e análise",
            effect="allow",
            channels=["telegram"],
            users=["*"],
            agents=["webmcp", "apex"],
            domains=["sports", "search"],
            commands=["/apex", "/buscar", "/jogos", "/aovivo", "/escalação", "/notícias"],
            priority=50
        )
        orch.policy_engine.add_rule(allow_rule)
        
        # Test apex command with telegram
        allowed, reason = orch._check_policy("/apex", channel_type="telegram", user_id="any_user")
        assert allowed is True, "Command /apex should be allowed for telegram channel"

    def test_cli_can_flow_new(self):
        """Testa se channel=cli, /flow-new → allowed."""
        orch = Orchestrator()
        
        # Add the CLI allow all rule
        cli_rule = PolicyRule(
            rule_id="allow-cli-all",
            description="CLI local tem acesso total",
            effect="allow",
            channels=["cli", "internal"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=80
        )
        orch.policy_engine.add_rule(cli_rule)
        
        # Test flow-new command with cli
        allowed, reason = orch._check_policy("/flow-new", channel_type="cli", user_id="any_user")
        assert allowed is True, "Command /flow-new should be allowed for cli channel"

    def test_any_channel_can_check_status(self):
        """Testa se channel=*, /flow-status → allowed."""
        orch = Orchestrator()
        
        # Add the read-only default rule
        default_rule = PolicyRule(
            rule_id="allow-read-only-defaults",
            description="Qualquer canal pode consultar status e listar templates",
            effect="allow",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["/flow-status", "/flow-runs", "/flow-templates"],
            priority=10
        )
        orch.policy_engine.add_rule(default_rule)
        
        # Test flow-status command with various channels
        for channel in ["telegram", "cli", "web", "discord"]:
            allowed, reason = orch._check_policy("/flow-status", channel_type=channel, user_id="any_user")
            assert allowed is True, f"Command /flow-status should be allowed for {channel} channel"

    def test_policy_check_exception_defaults_allow(self):
        """Testa se engine com erro → allowed=True."""
        orch = Orchestrator()
        
        # Temporarily replace the check method to raise an exception
        original_check = orch.policy_engine.check
        def error_check(*args, **kwargs):
            raise Exception("Policy engine error")
        
        orch.policy_engine.check = error_check
        
        try:
            # Test that it defaults to True despite the error
            allowed, reason = orch._check_policy("/any-command", channel_type="telegram", user_id="any_user")
            assert allowed is True, "Should default to True when policy engine fails"
            assert "Erro na verificação de política" in reason
        finally:
            # Restore original method
            orch.policy_engine.check = original_check