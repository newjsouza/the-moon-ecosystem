"""tests/test_dashboard_api.py — Testes da API do dashboard"""

import json
from unittest.mock import Mock, patch
from apex_dashboard.api import (
    _handle_status,
    _handle_flows,
    _handle_runs,
    _handle_scheduler,
    _handle_skills,
    _handle_policy,
    _handle_policy_check,
    _handle_templates,
    _handle_health,
    _handle_api
)


class TestDashboardAPI:
    def test_api_status_structure(self):
        """Testa /api/status retorna campos corretos."""
        data, status = _handle_status()
        
        assert status == 200
        assert "version" in data
        assert "uptime" in data
        assert "timestamp" in data
        assert "modules" in data
        assert "flow_registry" in data["modules"]
        assert "template_registry" in data["modules"]
        assert "scheduler_jobs" in data["modules"]
        assert "policy_rules" in data["modules"]
        assert "skill_count" in data["modules"]

    def test_api_flows_structure(self):
        """Testa /api/flows retorna lista."""
        data, status = _handle_flows()
        
        assert status == 200
        assert "flows" in data
        assert isinstance(data["flows"], list)

    def test_api_runs_structure(self):
        """Testa /api/runs retorna runs e total."""
        # Mock the flow run store
        with patch('apex_dashboard.api.get_flow_run_store') as mock_get_store:
            mock_store = Mock()
            mock_store.list_runs.return_value = []
            mock_get_store.return_value = mock_store
            
            data, status = _handle_runs("/api/runs", {})
            
            assert status == 200
            assert "runs" in data
            assert "total" in data
            assert data["total"] == 0

    def test_api_runs_with_filter(self):
        """Testa /api/runs?flow=apex_pipeline filtra corretamente."""
        # Mock the flow run store
        with patch('apex_dashboard.api.get_flow_run_store') as mock_get_store:
            mock_store = Mock()
            mock_store.list_runs.return_value = []
            mock_get_store.return_value = mock_store
            
            query_params = {"flow": ["apex_pipeline"]}
            data, status = _handle_runs("/api/runs", query_params)
            
            # Verify that list_runs was called with the flow name
            mock_store.list_runs.assert_called_once_with("apex_pipeline", None)
            
            assert status == 200
            assert "runs" in data
            assert "total" in data

    def test_api_scheduler_structure(self):
        """Testa /api/scheduler retorna jobs e totais."""
        # Mock the scheduler
        with patch('apex_dashboard.api.get_flow_scheduler') as mock_get_scheduler:
            mock_scheduler = Mock()
            mock_job = Mock()
            mock_job.job_id = "test-job"
            mock_job.flow_name = "test-flow"
            mock_job.schedule_type = "daily"
            mock_job.time_of_day = "07:30"
            mock_job.interval_minutes = 0
            mock_job.enabled = True
            mock_job.next_run_at = 1234567890
            mock_job.run_count = 5
            mock_job.last_run_at = 1234567880
            mock_scheduler.list_jobs.return_value = [mock_job]
            mock_get_scheduler.return_value = mock_scheduler
            
            data, status = _handle_scheduler("/api/scheduler", "GET", None)
            
            assert status == 200
            assert "jobs" in data
            assert "total" in data
            assert "enabled" in data
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["job_id"] == "test-job"

    def test_api_scheduler_enable(self):
        """Testa POST /api/scheduler/<id>/enable funciona."""
        # Mock the scheduler
        with patch('apex_dashboard.api.get_flow_scheduler') as mock_get_scheduler:
            mock_scheduler = Mock()
            mock_scheduler.enable_job.return_value = True
            mock_get_scheduler.return_value = mock_scheduler
            
            data, status = _handle_scheduler("/api/scheduler/test-job/enable", "POST", b"")
            
            assert status == 200
            assert data["job_id"] == "test-job"
            assert data["enabled"] is True
            assert data["ok"] is True
            mock_scheduler.enable_job.assert_called_once_with("test-job")

    def test_api_scheduler_disable(self):
        """Testa POST /api/scheduler/<id>/disable funciona."""
        # Mock the scheduler
        with patch('apex_dashboard.api.get_flow_scheduler') as mock_get_scheduler:
            mock_scheduler = Mock()
            mock_scheduler.disable_job.return_value = True
            mock_get_scheduler.return_value = mock_scheduler
            
            data, status = _handle_scheduler("/api/scheduler/test-job/disable", "POST", b"")
            
            assert status == 200
            assert data["job_id"] == "test-job"
            assert data["enabled"] is False
            assert data["ok"] is True
            mock_scheduler.disable_job.assert_called_once_with("test-job")

    def test_api_skills_structure(self):
        """Testa /api/skills retorna skills e by_domain."""
        # Mock the skill registry
        with patch('apex_dashboard.api.get_skill_registry') as mock_get_registry:
            mock_skill = Mock()
            mock_skill.name = "test-skill"
            mock_skill.description = "Test skill description"
            mock_skill.domains = ["web", "tools"]
            mock_registry = Mock()
            mock_registry.list_all.return_value = [mock_skill]
            mock_get_registry.return_value = mock_registry
            
            data, status = _handle_skills()
            
            assert status == 200
            assert "skills" in data
            assert "total" in data
            assert "by_domain" in data
            assert len(data["skills"]) == 1
            assert data["skills"][0]["name"] == "test-skill"
            assert "web" in data["by_domain"]
            assert "test-skill" in data["by_domain"]["web"]

    def test_api_policy_structure(self):
        """Testa /api/policy retorna rules e stats."""
        # Mock the policy engine
        with patch('apex_dashboard.api.get_policy_engine') as mock_get_engine:
            mock_rule = Mock()
            mock_rule.rule_id = "test-rule"
            mock_rule.effect = "allow"
            mock_rule.priority = 10
            mock_rule.description = "Test rule"
            mock_rule.channels = ["*"]
            mock_rule.commands = ["*"]
            mock_engine = Mock()
            mock_engine.list_rules.return_value = [mock_rule]
            mock_get_engine.return_value = mock_engine
            
            data, status = _handle_policy()
            
            assert status == 200
            assert "rules" in data
            assert "total" in data
            assert "stats" in data
            assert len(data["rules"]) == 1
            assert data["rules"][0]["rule_id"] == "test-rule"

    def test_api_policy_check(self):
        """Testa POST /api/policy/check retorna allowed e reason."""
        # Mock the policy engine
        with patch('apex_dashboard.api.get_policy_engine') as mock_get_engine:
            mock_decision = Mock()
            mock_decision.allowed = True
            mock_decision.reason = "Allowed by rule"
            mock_decision.rule_id = "test-rule"
            mock_engine = Mock()
            mock_engine.check.return_value = mock_decision
            mock_get_engine.return_value = mock_engine
            
            body = json.dumps({"channel": "cli", "user": "johnathan", "command": "/test"}).encode()
            data, status = _handle_policy_check("POST", body)
            
            assert status == 200
            assert "allowed" in data
            assert "reason" in data
            assert "rule_id" in data
            assert data["allowed"] is True
            assert data["reason"] == "Allowed by rule"
            
            # Verify that check was called with the correct parameters
            mock_engine.check.assert_called_once()

    def test_api_templates_structure(self):
        """Testa /api/templates retorna templates."""
        # Mock the template registry
        with patch('apex_dashboard.api.get_template_registry') as mock_get_registry:
            mock_var = Mock()
            mock_var.name = "test_var"
            mock_var.type = "str"
            mock_var.description = "Test variable"
            mock_var.default = "default_value"
            
            mock_template = Mock()
            mock_template.name = "test-template"
            mock_template.domain = "test-domain"
            mock_template.description = "Test template"
            mock_template.variables = [mock_var]
            mock_template.tags = ["tag1", "tag2"]
            
            mock_registry = Mock()
            mock_registry.list_templates.return_value = [mock_template]
            mock_get_registry.return_value = mock_registry
            
            data, status = _handle_templates()
            
            assert status == 200
            assert "templates" in data
            assert "total" in data
            assert len(data["templates"]) == 1
            assert data["templates"][0]["name"] == "test-template"
            assert len(data["templates"][0]["variables"]) == 1

    def test_api_health(self):
        """Testa /api/health retorna status=ok."""
        data, status = _handle_health()
        
        assert status == 200
        assert "status" in data
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_api_unknown_path(self):
        """Testa path desconhecido retorna 404."""
        data, status = _handle_api("/api/unknown/path", {}, None, "GET")
        
        assert status == 404
        assert "error" in data
        assert data["status"] == 404