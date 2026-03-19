"""tests/test_dashboard_integration.py — Testes de integração da API do dashboard"""

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


class TestDashboardIntegration:
    def test_api_imports_clean(self):
        """Testa todos os módulos importam sem erro."""
        from apex_dashboard.api import start_api_server, MoonDashboardAPIHandler
        assert start_api_server is not None
        assert MoonDashboardAPIHandler is not None

    def test_all_endpoints_return_dicts(self):
        """Testa cada handler retorna dict válido."""
        # Test status
        data, status = _handle_status()
        assert isinstance(data, dict)
        assert status == 200
        
        # Test flows
        data, status = _handle_flows()
        assert isinstance(data, dict)
        assert status == 200
        
        # Test runs (with mocked store)
        with patch('apex_dashboard.api.get_flow_run_store') as mock_get_store:
            mock_store = Mock()
            mock_store.list_runs.return_value = []
            mock_get_store.return_value = mock_store
            data, status = _handle_runs("/api/runs", {})
            assert isinstance(data, dict)
            assert status == 200
        
        # Test scheduler (with mocked scheduler)
        with patch('apex_dashboard.api.get_flow_scheduler') as mock_get_scheduler:
            mock_scheduler = Mock()
            mock_scheduler.list_jobs.return_value = []
            mock_get_scheduler.return_value = mock_scheduler
            data, status = _handle_scheduler("/api/scheduler", "GET", None)
            assert isinstance(data, dict)
            assert status == 200
        
        # Test skills (with mocked registry)
        with patch('apex_dashboard.api.get_skill_registry') as mock_get_registry:
            mock_registry = Mock()
            mock_registry.list_all.return_value = []
            mock_get_registry.return_value = mock_registry
            data, status = _handle_skills()
            assert isinstance(data, dict)
            assert status == 200
        
        # Test policy (with mocked engine)
        with patch('apex_dashboard.api.get_policy_engine') as mock_get_engine:
            mock_engine = Mock()
            mock_engine.list_rules.return_value = []
            mock_get_engine.return_value = mock_engine
            data, status = _handle_policy()
            assert isinstance(data, dict)
            assert status == 200
        
        # Test templates (with mocked registry)
        with patch('apex_dashboard.api.get_template_registry') as mock_get_registry:
            mock_registry = Mock()
            mock_registry.list_templates.return_value = []
            mock_get_registry.return_value = mock_registry
            data, status = _handle_templates()
            assert isinstance(data, dict)
            assert status == 200
        
        # Test health
        data, status = _handle_health()
        assert isinstance(data, dict)
        assert status == 200

    def test_status_has_real_module_counts(self):
        """Testa contagens refletem módulos reais."""
        data, status = _handle_status()
        assert status == 200
        assert isinstance(data['modules']['flow_registry'], int)
        assert isinstance(data['modules']['template_registry'], int)
        assert isinstance(data['modules']['scheduler_jobs'], int)
        assert isinstance(data['modules']['policy_rules'], int)
        assert isinstance(data['modules']['skill_count'], int)

    def test_runs_filter_by_flow(self):
        """Testa filtro por flow_name funciona."""
        with patch('apex_dashboard.api.get_flow_run_store') as mock_get_store:
            mock_store = Mock()
            mock_store.list_runs.return_value = []
            mock_get_store.return_value = mock_store
            
            query_params = {"flow": ["test_flow"]}
            data, status = _handle_runs("/api/runs", query_params)
            
            # Verify that list_runs was called with the flow name
            mock_store.list_runs.assert_called_once_with("test_flow", None)
            assert status == 200

    def test_runs_filter_by_status(self):
        """Testa filtro por status funciona."""
        with patch('apex_dashboard.api.get_flow_run_store') as mock_get_store:
            mock_store = Mock()
            mock_store.list_runs.return_value = []
            mock_get_store.return_value = mock_store
            
            query_params = {"status": ["success"]}
            data, status = _handle_runs("/api/runs", query_params)
            
            # Verify that list_runs was called with the status
            mock_store.list_runs.assert_called_once_with(None, "success")
            assert status == 200

    def test_scheduler_enable_disable_toggle(self):
        """Testa toggle persiste em memória."""
        with patch('apex_dashboard.api.get_flow_scheduler') as mock_get_scheduler:
            mock_scheduler = Mock()
            mock_scheduler.enable_job.return_value = True
            mock_scheduler.disable_job.return_value = True
            mock_get_scheduler.return_value = mock_scheduler
            
            # Test enable
            data, status = _handle_scheduler("/api/scheduler/job123/enable", "POST", b"")
            assert status == 200
            assert data["ok"] is True
            mock_scheduler.enable_job.assert_called_once_with("job123")
            
            # Reset mock
            mock_scheduler.reset_mock()
            mock_scheduler.disable_job.return_value = True
            
            # Test disable
            data, status = _handle_scheduler("/api/scheduler/job123/disable", "POST", b"")
            assert status == 200
            assert data["ok"] is True
            mock_scheduler.disable_job.assert_called_once_with("job123")

    def test_skills_by_domain_grouping(self):
        """Testa by_domain agrupa corretamente."""
        with patch('apex_dashboard.api.get_skill_registry') as mock_get_registry:
            mock_skill1 = Mock()
            mock_skill1.name = "web_skill"
            mock_skill1.description = "Web skill"
            mock_skill1.domains = ["web", "tools"]
            
            mock_skill2 = Mock()
            mock_skill2.name = "dev_skill"
            mock_skill2.description = "Dev skill"
            mock_skill2.domains = ["dev", "tools"]
            
            mock_registry = Mock()
            mock_registry.list_all.return_value = [mock_skill1, mock_skill2]
            mock_get_registry.return_value = mock_registry
            
            data, status = _handle_skills()
            
            assert status == 200
            assert "web" in data["by_domain"]
            assert "tools" in data["by_domain"]  # Both skills have "tools"
            assert "dev" in data["by_domain"]
            assert "web_skill" in data["by_domain"]["web"]
            assert "web_skill" in data["by_domain"]["tools"]
            assert "dev_skill" in data["by_domain"]["dev"]
            assert "dev_skill" in data["by_domain"]["tools"]

    def test_policy_check_owner_allowed(self):
        """Testa johnathan sempre permitido."""
        with patch('apex_dashboard.api.get_policy_engine') as mock_get_engine:
            mock_decision = Mock()
            mock_decision.allowed = True
            mock_decision.reason = "Allowed by owner rule"
            mock_decision.rule_id = "allow-owner-all"
            mock_engine = Mock()
            mock_engine.check.return_value = mock_decision
            mock_get_engine.return_value = mock_engine
            
            import json
            body = json.dumps({
                "channel": "cli", 
                "user": "johnathan", 
                "command": "/admin"
            }).encode()
            data, status = _handle_policy_check("POST", body)
            
            assert status == 200
            assert data["allowed"] is True
            assert "owner" in data["reason"] or "allow" in data["reason"].lower()
            
            # Verify that check was called with correct params
            mock_engine.check.assert_called_once()

    def test_policy_check_deny_applies(self):
        """Testa deny rule aplicada corretamente."""
        with patch('apex_dashboard.api.get_policy_engine') as mock_get_engine:
            mock_decision = Mock()
            mock_decision.allowed = False
            mock_decision.reason = "Denied by rule"
            mock_decision.rule_id = "deny-rule"
            mock_engine = Mock()
            mock_engine.check.return_value = mock_decision
            mock_get_engine.return_value = mock_engine
            
            import json
            body = json.dumps({
                "channel": "telegram", 
                "user": "some_user", 
                "command": "/flow-retry"
            }).encode()
            data, status = _handle_policy_check("POST", body)
            
            assert status == 200
            assert data["allowed"] is False
            assert data["rule_id"] == "deny-rule"
            
            # Verify that check was called with correct params
            mock_engine.check.assert_called_once()

    def test_health_returns_ok(self):
        """Testa health check ok."""
        data, status = _handle_health()
        assert status == 200
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_404_for_unknown_endpoint(self):
        """Testa path inválido → erro controlado."""
        data, status = _handle_api("/api/nonexistent", {}, None, "GET")
        assert status == 404
        assert "error" in data
        assert data["status"] == 404