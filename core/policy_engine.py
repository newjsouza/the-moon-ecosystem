"""
core/policy_engine.py
Policy engine for access control in The Moon ecosystem.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import os


@dataclass
class PolicyRule:
    """Represents a policy rule for access control."""
    rule_id: str
    description: str
    effect: str  # "allow" | "deny"
    channels: List[str]  # ["telegram", "cli", "*"] — * = todos
    users: List[str]  # ["*", "johnathan", "user123"]
    agents: List[str]  # ["apex", "blog_writer", "*"]
    domains: List[str]  # ["sports", "blog", "*"]
    commands: List[str]  # ["/apex", "/flow-new", "*"]
    priority: int = 0  # maior prioridade vence em conflito


@dataclass
class PolicyDecision:
    """Represents the result of a policy check."""
    allowed: bool
    rule_id: str
    reason: str


class PolicyEngine:
    """Policy engine for access control in The Moon ecosystem."""
    
    def __init__(self):
        self._rules: List[PolicyRule] = []
        self._lock = threading.Lock()

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule."""
        with self._lock:
            # Remove any existing rule with the same ID
            self._rules = [r for r in self._rules if r.rule_id != rule.rule_id]
            self._rules.append(rule)
            # Keep the list sorted by priority (highest first)
            self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a policy rule by ID."""
        with self._lock:
            original_len = len(self._rules)
            self._rules = [r for r in self._rules if r.rule_id != rule_id]
            return len(self._rules) != original_len

    def list_rules(self) -> List[PolicyRule]:
        """List all policy rules."""
        with self._lock:
            return self._rules[:]

    def _matches_field(self, rule_values: List[str], actual: str) -> bool:
        """Check if a field matches the rule values."""
        return "*" in rule_values or actual in rule_values

    def check(
        self,
        channel_type: str,
        user_id: str,
        agent: str = "*",
        domain: str = "*",
        command: str = "*"
    ) -> PolicyDecision:
        """Check if an action is allowed based on the policy rules."""
        with self._lock:
            for rule in self._rules:
                # Check if all fields match
                if (self._matches_field(rule.channels, channel_type) and
                    self._matches_field(rule.users, user_id) and
                    self._matches_field(rule.agents, agent) and
                    self._matches_field(rule.domains, domain) and
                    self._matches_field(rule.commands, command)):
                    
                    return PolicyDecision(
                        allowed=(rule.effect == "allow"),
                        rule_id=rule.rule_id,
                        reason=f"Matched rule '{rule.rule_id}': {rule.description}"
                    )
        
        # If no rule matched, default to allowing
        return PolicyDecision(
            allowed=True,
            rule_id="default",
            reason="Sem regras correspondentes - padrão é permitir"
        )

    def load_from_file(self, path: str) -> int:
        """Load policy rules from a JSON file."""
        if not os.path.exists(path):
            return 0
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        loaded_count = 0
        for rule_data in data.get("rules", []):
            try:
                rule = PolicyRule(**rule_data)
                self.add_rule(rule)
                loaded_count += 1
            except Exception:
                # Skip invalid rules
                continue
        
        return loaded_count

    def save_to_file(self, path: str) -> None:
        """Save policy rules to a JSON file."""
        rules_data = [asdict(rule) for rule in self.list_rules()]
        data = {"rules": rules_data}
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the policy engine."""
        with self._lock:
            total_rules = len(self._rules)
            allow_rules = sum(1 for r in self._rules if r.effect == "allow")
            deny_rules = sum(1 for r in self._rules if r.effect == "deny")
            
            return {
                "total_rules": total_rules,
                "allow_rules": allow_rules,
                "deny_rules": deny_rules
            }


# Singleton instance
_policy_engine = None
_policy_lock = threading.Lock()


def get_policy_engine() -> PolicyEngine:
    """Get singleton instance of PolicyEngine."""
    global _policy_engine
    
    with _policy_lock:
        if _policy_engine is None:
            _policy_engine = PolicyEngine()
    
    return _policy_engine