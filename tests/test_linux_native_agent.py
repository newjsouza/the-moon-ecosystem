"""Tests for LinuxNativeAgent — mocked subprocess, zero system deps."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestLinuxNative:

    def test_import(self):
        from core.linux_native import LinuxNative, AudioDevice, SystemInfo
        ln = LinuxNative()
        assert ln is not None

    @pytest.mark.asyncio
    async def test_run_success(self):
        from core.linux_native import LinuxNative
        ln = LinuxNative()
        result = await ln._run("echo hello")
        assert result is not None
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_failure_returns_none(self):
        from core.linux_native import LinuxNative
        ln = LinuxNative()
        result = await ln._run("command_that_does_not_exist_xyz_abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_volume_wpctl(self):
        from core.linux_native import LinuxNative
        ln = LinuxNative()
        with patch.object(ln, "_run", new_callable=AsyncMock, return_value="Volume: 0.65\n"):
            vol = await ln.get_volume()
        assert abs(vol - 65.0) < 0.1

    @pytest.mark.asyncio
    async def test_set_volume_clamps(self):
        from core.linux_native import LinuxNative
        ln = LinuxNative()
        with patch.object(ln, "_run", new_callable=AsyncMock, return_value="") as mock_run:
            await ln.set_volume(150.0)
            call_args = mock_run.call_args[0][0]
            assert "1.00" in call_args  # clamped to 100%

    @pytest.mark.asyncio
    async def test_toggle_mic_returns_bool(self):
        from core.linux_native import LinuxNative
        ln = LinuxNative()
        with patch.object(ln, "_run", new_callable=AsyncMock, return_value="Volume: 0.80 [MUTED]"):
            result = await ln.toggle_mic()
        assert isinstance(result, bool)
        assert result is True

    @pytest.mark.asyncio
    async def test_read_ram(self):
        from core.linux_native import LinuxNative
        ln = LinuxNative()
        used, total = await ln._read_ram()
        assert total > 0
        assert used >= 0
        assert used <= total

    @pytest.mark.asyncio
    async def test_battery_not_found(self):
        from core.linux_native import LinuxNative
        from unittest.mock import patch as p
        ln = LinuxNative()
        with p("pathlib.Path.glob", return_value=[]):
            result = await ln.get_battery_status()
        assert result["battery"] is None
        assert result["status"] == "not_found"


class TestLinuxNativeAgent:

    def setup_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def teardown_method(self):
        from core.observability.observer import MoonObserver
        MoonObserver.reset_instance()

    def test_import(self):
        from agents.linux_native_agent import LinuxNativeAgent
        agent = LinuxNativeAgent()
        assert agent.AGENT_ID == "linux_native"

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        from agents.linux_native_agent import LinuxNativeAgent
        agent = LinuxNativeAgent()
        result = await agent._execute("invalid_cmd")
        assert result.success is False
        assert "Unknown command" in result.error

    @pytest.mark.asyncio
    async def test_status_command(self):
        from agents.linux_native_agent import LinuxNativeAgent
        from core.linux_native import SystemInfo
        agent = LinuxNativeAgent()
        mock_info = SystemInfo(
            cpu_pct=15.2, ram_pct=45.0, ram_used_gb=3.6, ram_total_gb=8.0,
            uptime_seconds=7200, active_window="Terminal", desktop_session="GNOME",
            audio_sink_volume=65.0, mic_volume=80.0, is_mic_muted=False
        )
        with patch.object(agent.native, "get_system_info", new_callable=AsyncMock, return_value=mock_info), \
             patch.object(agent.native, "get_battery_status", new_callable=AsyncMock,
                          return_value={"battery": None, "level_pct": None, "status": "not_found"}):
            result = await agent._execute("status")
        assert result.success is True
        assert result.data["cpu_pct"] == 15.2
        assert result.data["uptime_human"] == "2h 0m"

    @pytest.mark.asyncio
    async def test_volume_get(self):
        from agents.linux_native_agent import LinuxNativeAgent
        agent = LinuxNativeAgent()
        with patch.object(agent.native, "get_volume", new_callable=AsyncMock, return_value=70.0):
            result = await agent._execute("volume")
        assert result.success is True
        assert result.data["volume_pct"] == 70.0

    @pytest.mark.asyncio
    async def test_mute_toggle(self):
        from agents.linux_native_agent import LinuxNativeAgent
        agent = LinuxNativeAgent()
        with patch.object(agent.native, "toggle_mute", new_callable=AsyncMock, return_value=True):
            result = await agent._execute("mute")
        assert result.success is True
        assert result.data["muted"] is True

    @pytest.mark.asyncio
    async def test_notify_requires_body(self):
        from agents.linux_native_agent import LinuxNativeAgent
        agent = LinuxNativeAgent()
        result = await agent._execute("notify", title="Test")
        assert result.success is False
        assert "body" in result.error

    @pytest.mark.asyncio
    async def test_battery_command(self):
        from agents.linux_native_agent import LinuxNativeAgent
        agent = LinuxNativeAgent()
        with patch.object(agent.native, "get_battery_status", new_callable=AsyncMock,
                          return_value={"battery": "BAT0", "level_pct": 78, "status": "Discharging", "charging": False}):
            result = await agent._execute("battery")
        assert result.success is True
        assert result.data["level_pct"] == 78

    @pytest.mark.asyncio
    async def test_hotkey_no_args(self):
        from agents.linux_native_agent import LinuxNativeAgent
        agent = LinuxNativeAgent()
        result = await agent._execute("hotkey")
        assert result.success is False
