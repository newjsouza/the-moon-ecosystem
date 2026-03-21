"""Tests for WorkspaceMonitor v2 — mocked server, zero real HTTP calls."""
import pytest
from apps.workspace_monitor.backend.server import HAS_FASTAPI

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")


class TestServerModule:
    def test_import(self):
        assert HAS_FASTAPI is True

    def test_app_exists(self):
        from apps.workspace_monitor.backend import server
        assert hasattr(server, "app")

    def test_event_buffer_accessible(self):
        from apps.workspace_monitor.backend import server
        assert hasattr(server, "_event_buffer")
        assert isinstance(server._event_buffer, list)

    def test_connection_manager_init(self):
        from apps.workspace_monitor.backend.server import ConnectionManager
        cm = ConnectionManager()
        assert cm.live_connections == []
        assert cm.metrics_connections == []

    def test_connection_manager_disconnect(self):
        from apps.workspace_monitor.backend.server import ConnectionManager
        from unittest.mock import MagicMock
        cm = ConnectionManager()
        mock_ws = MagicMock()
        cm.live_connections = [mock_ws]
        cm.disconnect(mock_ws)
        assert mock_ws not in cm.live_connections

    def test_frontend_html_exists(self):
        from pathlib import Path
        html = Path("apps/workspace_monitor/frontend/index.html")
        assert html.exists()
        content = html.read_text()
        assert "The Moon" in content
        assert "ws://" in content

    def test_launch_module_exists(self):
        from pathlib import Path
        assert Path("apps/workspace_monitor/launch.py").exists()

    @pytest.mark.asyncio
    async def test_broadcast_live_empty_connections(self):
        from apps.workspace_monitor.backend.server import ConnectionManager
        cm = ConnectionManager()
        await cm.broadcast_live({"type": "test", "data": "hello"})
