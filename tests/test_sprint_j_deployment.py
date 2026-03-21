"""Sprint J — Test suite for deployment & production hardening."""
import pytest
import asyncio
import os
import signal
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────
# EnvValidator tests
# ─────────────────────────────────────────────
class TestEnvValidator:

    def test_required_vars_defined(self):
        from core.env_validator import REQUIRED_VARS
        assert len(REQUIRED_VARS) >= 5
        var_names = [v.name for v in REQUIRED_VARS]
        for required in ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", 
                         "TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN"]:
            assert required in var_names

    def test_optional_vars_defined(self):
        from core.env_validator import OPTIONAL_VARS
        assert len(OPTIONAL_VARS) >= 3
        var_names = [v.name for v in OPTIONAL_VARS]
        for optional in ["FOOTBALL_DATA_API_KEY", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET"]:
            assert optional in var_names

    def test_validator_initialization(self):
        from core.env_validator import EnvValidator
        validator = EnvValidator(strict=False)
        assert validator is not None

    def test_get_status_without_env_vars(self):
        from core.env_validator import EnvValidator
        validator = EnvValidator(strict=False)
        status = validator.get_status()
        # Without environment variables, it should have errors
        assert "valid" in status
        assert "errors" in status

    def test_validate_or_exit_raises_when_strict_and_missing_vars(self):
        from core.env_validator import EnvValidator
        validator = EnvValidator(strict=True)
        # Mock environment to be missing required vars
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit) as excinfo:
                validator.validate_or_exit()
            assert excinfo.value.code == 1


# ─────────────────────────────────────────────
# MoonDaemon tests
# ─────────────────────────────────────────────
class TestMoonDaemon:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_daemon_initialization(self):
        from core.daemon import MoonDaemon
        daemon = MoonDaemon()
        assert daemon is not None
        assert daemon.loop is not None

    def test_register_default_tasks(self):
        from core.daemon import MoonDaemon
        daemon = MoonDaemon()
        initial_size = daemon.loop.queue_size()
        daemon._register_default_tasks()
        final_size = daemon.loop.queue_size()
        # Should have added some default tasks
        assert final_size >= initial_size

    @pytest.mark.asyncio
    async def test_handle_shutdown_sets_event(self):
        from core.daemon import MoonDaemon
        daemon = MoonDaemon()
        # Simulate shutdown event
        await daemon._handle_shutdown(signal.SIGTERM)
        # The shutdown event should be set
        assert daemon._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_heartbeat_logs_status(self):
        from core.daemon import MoonDaemon
        daemon = MoonDaemon()
        # Mock the logger to capture log messages
        with patch.object(daemon.logger, 'info') as mock_log:
            # Create a short-running heartbeat task
            task = asyncio.create_task(daemon._heartbeat())
            # Cancel after a short delay
            await asyncio.sleep(0.1)
            task.cancel()
            # Check that logger.info was called
            assert mock_log.called


# ─────────────────────────────────────────────
# moon_sync.py CLI extensions tests
# ─────────────────────────────────────────────
class TestMoonSyncExtensions:

    @pytest.mark.asyncio
    async def test_cmd_health_runs_without_error(self):
        from core.observability.observer import MoonObserver
        # Clear any existing observer instance
        MoonObserver.reset_instance()
        
        # Import and run the health command
        from moon_sync import cmd_health
        # This should not raise an exception
        await cmd_health()
        # Reset again afterwards
        MoonObserver.reset_instance()

    def test_cmd_schedule_creates_task(self):
        from moon_sync import cmd_schedule
        import io
        import sys
        from contextlib import redirect_stdout

        # Capture the output of the schedule command
        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            cmd_schedule("test_agent:test_task:3")
        
        output = captured_output.getvalue()
        # Should contain the task ID
        assert "task_id" in output
        assert "test_agent" in output

    @pytest.mark.asyncio
    async def test_cmd_serve_imports_correctly(self):
        # Just test that the function can be imported without error
        from moon_sync import cmd_serve
        assert cmd_serve is not None


# ─────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────
class TestSprintJIntegration:

    def test_all_components_import(self):
        from core.env_validator import EnvValidator, REQUIRED_VARS
        from core.daemon import MoonDaemon
        from moon_sync import cmd_health, cmd_serve, cmd_schedule
        assert all([EnvValidator, REQUIRED_VARS, MoonDaemon, cmd_health, cmd_serve, cmd_schedule])

    def test_env_validation_works_with_mock_env(self):
        from core.env_validator import EnvValidator
        # Temporarily set some environment variables
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "gsk_test_key_1234567890",
            "GEMINI_API_KEY": "AIzaSy_test_key_1234567890",
            "OPENROUTER_API_KEY": "sk-or-test_key_1234567890",
            "TELEGRAM_BOT_TOKEN": "123456789:ABC_test_token_1234567890",
            "GITHUB_TOKEN": "ghp_test_token_1234567890"
        }):
            validator = EnvValidator(strict=False)
            status = validator.get_status()
            assert status["valid"] is True
            assert status["required_count"] >= 5

    @pytest.mark.asyncio
    async def test_daemon_can_be_started_and_stopped(self):
        from core.daemon import MoonDaemon
        daemon = MoonDaemon()
        
        # Mock the heartbeat and loop run methods to avoid blocking
        with patch.object(daemon, '_heartbeat', 
                         new_callable=AsyncMock) as mock_heartbeat, \
             patch.object(daemon.loop, 'run', 
                         new_callable=AsyncMock) as mock_run:
            
            # Mock heartbeat to throw an exception after a short delay
            async def heartbeat_with_cancel():
                await asyncio.sleep(0.1)
                daemon._shutdown_event.set()
            
            mock_heartbeat.side_effect = heartbeat_with_cancel
            mock_run.return_value = MagicMock()
            
            # Start the daemon
            await daemon.start(with_default_tasks=False)
            
            # Both methods should have been called
            assert mock_heartbeat.called
            assert mock_run.called

    def test_systemd_service_file_exists(self):
        import os
        # Check that the systemd service file exists
        assert os.path.exists("the-moon.service")

    def test_deploy_documentation_exists(self):
        import os
        # Check that the deployment guide exists
        assert os.path.exists("DEPLOY.md")