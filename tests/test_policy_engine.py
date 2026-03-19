"""tests/test_policy_engine.py — Testes do sistema de política de acesso"""

import json
import tempfile
import os
from core.policy_engine import PolicyEngine, PolicyRule, PolicyDecision, get_policy_engine


class TestPolicyEngine:
    def test_policy_rule_creation(self):
        """Testa PolicyRule com todos os campos."""
        rule = PolicyRule(
            rule_id="test_rule",
            description="Test rule description",
            effect="allow",
            channels=["telegram", "cli"],
            users=["user1", "user2"],
            agents=["agent1", "agent2"],
            domains=["domain1", "domain2"],
            commands=["/cmd1", "/cmd2"],
            priority=50
        )
        
        assert rule.rule_id == "test_rule"
        assert rule.description == "Test rule description"
        assert rule.effect == "allow"
        assert rule.channels == ["telegram", "cli"]
        assert rule.users == ["user1", "user2"]
        assert rule.agents == ["agent1", "agent2"]
        assert rule.domains == ["domain1", "domain2"]
        assert rule.commands == ["/cmd1", "/cmd2"]
        assert rule.priority == 50

    def test_policy_decision_creation(self):
        """Testa PolicyDecision com allowed e reason."""
        decision = PolicyDecision(allowed=True, rule_id="test_rule", reason="Test reason")
        
        assert decision.allowed is True
        assert decision.rule_id == "test_rule"
        assert decision.reason == "Test reason"

    def test_engine_singleton(self):
        """Testa singleton - mesma instância."""
        engine1 = get_policy_engine()
        engine2 = get_policy_engine()
        
        assert engine1 is engine2

    def test_engine_add_and_list_rules(self):
        """Testa adicionar regra e listar."""
        engine = PolicyEngine()
        rule = PolicyRule(
            rule_id="test_rule",
            description="Test rule",
            effect="allow",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=10
        )
        
        engine.add_rule(rule)
        rules = engine.list_rules()
        
        assert len(rules) == 1
        assert rules[0].rule_id == "test_rule"

    def test_engine_remove_rule(self):
        """Testa remover por rule_id."""
        engine = PolicyEngine()
        rule = PolicyRule(
            rule_id="test_rule",
            description="Test rule",
            effect="allow",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=10
        )
        
        engine.add_rule(rule)
        removed = engine.remove_rule("test_rule")
        
        assert removed is True
        assert len(engine.list_rules()) == 0

    def test_check_allow_exact(self):
        """Testa regra allow com match exato → allowed=True."""
        engine = PolicyEngine()
        rule = PolicyRule(
            rule_id="allow_exact",
            description="Allow exact match",
            effect="allow",
            channels=["telegram"],
            users=["user1"],
            agents=["agent1"],
            domains=["domain1"],
            commands=["/cmd1"],
            priority=10
        )
        
        engine.add_rule(rule)
        decision = engine.check(
            channel_type="telegram",
            user_id="user1",
            agent="agent1",
            domain="domain1",
            command="/cmd1"
        )
        
        assert decision.allowed is True
        assert decision.rule_id == "allow_exact"

    def test_check_deny_exact(self):
        """Testa regra deny com match exato → allowed=False."""
        engine = PolicyEngine()
        rule = PolicyRule(
            rule_id="deny_exact",
            description="Deny exact match",
            effect="deny",
            channels=["telegram"],
            users=["user1"],
            agents=["agent1"],
            domains=["domain1"],
            commands=["/cmd1"],
            priority=10
        )
        
        engine.add_rule(rule)
        decision = engine.check(
            channel_type="telegram",
            user_id="user1",
            agent="agent1",
            domain="domain1",
            command="/cmd1"
        )
        
        assert decision.allowed is False
        assert decision.rule_id == "deny_exact"

    def test_check_wildcard(self):
        """Testa regra com "*" faz match em qualquer valor."""
        engine = PolicyEngine()
        rule = PolicyRule(
            rule_id="wildcard_rule",
            description="Wildcard rule",
            effect="allow",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=10
        )
        
        engine.add_rule(rule)
        decision = engine.check(
            channel_type="any_channel",
            user_id="any_user",
            agent="any_agent",
            domain="any_domain",
            command="any_cmd"
        )
        
        assert decision.allowed is True
        assert decision.rule_id == "wildcard_rule"

    def test_check_priority(self):
        """Testa regra de maior prioridade vence em conflito."""
        engine = PolicyEngine()
        # Add a deny rule with lower priority
        deny_rule = PolicyRule(
            rule_id="deny_low_priority",
            description="Low priority deny",
            effect="deny",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=10
        )
        
        # Add an allow rule with higher priority
        allow_rule = PolicyRule(
            rule_id="allow_high_priority",
            description="High priority allow",
            effect="allow",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=20
        )
        
        engine.add_rule(deny_rule)
        engine.add_rule(allow_rule)
        
        decision = engine.check(
            channel_type="any_channel",
            user_id="any_user",
            agent="any_agent",
            domain="any_domain",
            command="any_cmd"
        )
        
        # Higher priority rule should win
        assert decision.allowed is True
        assert decision.rule_id == "allow_high_priority"

    def test_check_no_match_default_allow(self):
        """Testa sem regras → allowed=True."""
        engine = PolicyEngine()
        decision = engine.check(
            channel_type="any_channel",
            user_id="any_user",
            agent="any_agent",
            domain="any_domain",
            command="any_cmd"
        )
        
        assert decision.allowed is True
        assert decision.rule_id == "default"

    def test_load_from_file(self):
        """Testa carregar default_policy.json."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            policy_data = {
                "rules": [
                    {
                        "rule_id": "loaded_rule",
                        "description": "Loaded rule",
                        "effect": "allow",
                        "channels": ["cli"],
                        "users": ["admin"],
                        "agents": ["*"],
                        "domains": ["*"],
                        "commands": ["/admin"],
                        "priority": 30
                    }
                ]
            }
            json.dump(policy_data, f)
            temp_file = f.name
        
        try:
            engine = PolicyEngine()
            count = engine.load_from_file(temp_file)
            
            assert count == 1
            rules = engine.list_rules()
            assert len(rules) == 1
            assert rules[0].rule_id == "loaded_rule"
        finally:
            os.unlink(temp_file)

    def test_save_and_reload(self):
        """Testa salvar e recarregar round-trip."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            engine = PolicyEngine()
            original_rule = PolicyRule(
                rule_id="roundtrip_rule",
                description="Round trip rule",
                effect="allow",
                channels=["web"],
                users=["user"],
                agents=["agent"],
                domains=["domain"],
                commands=["/cmd"],
                priority=40
            )
            
            engine.add_rule(original_rule)
            engine.save_to_file(temp_file)
            
            # Create new engine and load from file
            new_engine = PolicyEngine()
            count = new_engine.load_from_file(temp_file)
            
            assert count == 1
            rules = new_engine.list_rules()
            assert len(rules) == 1
            assert rules[0].rule_id == "roundtrip_rule"
        finally:
            os.unlink(temp_file)

    def test_get_stats(self):
        """Testa stats retorna allow/deny corretos."""
        engine = PolicyEngine()
        allow_rule = PolicyRule(
            rule_id="allow_rule",
            description="Allow rule",
            effect="allow",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=10
        )
        
        deny_rule = PolicyRule(
            rule_id="deny_rule",
            description="Deny rule",
            effect="deny",
            channels=["*"],
            users=["*"],
            agents=["*"],
            domains=["*"],
            commands=["*"],
            priority=10
        )
        
        engine.add_rule(allow_rule)
        engine.add_rule(deny_rule)
        
        stats = engine.get_stats()
        
        assert stats["total_rules"] == 2
        assert stats["allow_rules"] == 1
        assert stats["deny_rules"] == 1

    def test_matches_field_wildcard(self):
        """Testa _matches_field(["*"], "qualquer") = True."""
        engine = PolicyEngine()
        
        # Test wildcard matching
        result = engine._matches_field(["*"], "any_value")
        assert result is True
        
        # Test non-wildcard matching
        result = engine._matches_field(["specific"], "specific")
        assert result is True
        
        # Test non-matching
        result = engine._matches_field(["specific"], "other")
        assert result is False

    def test_matches_field_exact(self):
        """Testa _matches_field(["telegram"], "telegram") = True."""
        engine = PolicyEngine()
        
        result = engine._matches_field(["telegram", "cli"], "telegram")
        assert result is True
        
        result = engine._matches_field(["telegram", "cli"], "cli")
        assert result is True
        
        result = engine._matches_field(["telegram", "cli"], "discord")
        assert result is False


class TestOrchestratorIntegration:
    def test_orchestrator_policy_engine(self):
        """Testa se policy_engine é inicializado no Orchestrator."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        
        # Verify policy engine exists
        assert hasattr(orch, 'policy_engine')
        assert orch.policy_engine is not None

    def test_check_policy_method(self):
        """Testa _check_policy() retorna tuple (bool, str)."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        
        # Verify method exists
        assert hasattr(orch, '_check_policy')
        
        # Test the method returns correct tuple format
        allowed, reason = orch._check_policy("/test", channel_type="cli")
        
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)

    def test_policy_command_registered(self):
        """Testa se /policy está no CommandRegistry."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        match = orch.registry.resolve("/policy list")
        assert match is not None, "Comando /policy não encontrado"
        entry, remainder = match
        assert remainder == "list"