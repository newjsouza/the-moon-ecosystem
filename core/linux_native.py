"""
core/linux_native.py — Low-level Linux system integration.

Provides zero-dependency abstractions over:
  - PipeWire / PulseAudio (audio via wpctl or pactl)
  - D-Bus / GNOME Shell (desktop automation via gdbus)
  - udev (hardware events via /sys and subprocess)
  - /proc (system metrics)

All operations use subprocess for maximum compatibility.
No pip dependencies required — uses system binaries.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Represents a PipeWire/PulseAudio audio device."""
    device_id: str
    name: str
    device_type: str        # "sink" (output) | "source" (input/mic)
    is_default: bool
    volume_pct: float       # 0.0 to 100.0
    is_muted: bool


@dataclass
class SystemInfo:
    """Snapshot of current system state."""
    cpu_pct: float
    ram_pct: float
    ram_used_gb: float
    ram_total_gb: float
    uptime_seconds: int
    active_window: str      # current focused window title
    desktop_session: str    # GNOME, KDE, etc.
    audio_sink_volume: float
    mic_volume: float
    is_mic_muted: bool


class LinuxNative:
    """
    Async Linux system integration layer.
    Uses subprocess + system binaries exclusively.
    """

    # ── Audio (PipeWire / PulseAudio) ─────────────────────────

    async def get_volume(self) -> float:
        """Get default audio sink volume (0-100)."""
        # Try wpctl first (PipeWire)
        result = await self._run("wpctl get-volume @DEFAULT_AUDIO_SINK@")
        if result and "Volume:" in result:
            match = re.search(r"Volume:\s*([\d.]+)", result)
            if match:
                return round(float(match.group(1)) * 100, 1)

        # Fallback: pactl (PulseAudio)
        result = await self._run(
            "pactl get-sink-volume @DEFAULT_SINK@"
        )
        if result:
            match = re.search(r"(\d+)%", result)
            if match:
                return float(match.group(1))

        return 0.0

    async def set_volume(self, pct: float) -> bool:
        """Set default audio sink volume (0-100)."""
        pct = max(0.0, min(100.0, pct))

        # Try wpctl
        result = await self._run(
            f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {pct/100:.2f}"
        )
        if result is not None:
            logger.info(f"Volume set to {pct}% via wpctl")
            return True

        # Fallback: pactl
        result = await self._run(
            f"pactl set-sink-volume @DEFAULT_SINK@ {int(pct)}%"
        )
        return result is not None

    async def toggle_mute(self) -> bool:
        """Toggle audio sink mute. Returns new muted state."""
        await self._run("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
        result = await self._run("wpctl get-volume @DEFAULT_AUDIO_SINK@")
        return result is not None and "MUTED" in result

    async def get_mic_volume(self) -> float:
        """Get default microphone (source) volume (0-100)."""
        result = await self._run("wpctl get-volume @DEFAULT_AUDIO_SOURCE@")
        if result and "Volume:" in result:
            match = re.search(r"Volume:\s*([\d.]+)", result)
            if match:
                return round(float(match.group(1)) * 100, 1)
        return 0.0

    async def mute_mic(self) -> bool:
        """Mute microphone."""
        result = await self._run(
            "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 1"
        )
        return result is not None

    async def unmute_mic(self) -> bool:
        """Unmute microphone."""
        result = await self._run(
            "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0"
        )
        return result is not None

    async def toggle_mic(self) -> bool:
        """Toggle microphone mute. Returns new muted state."""
        await self._run("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle")
        result = await self._run("wpctl get-volume @DEFAULT_AUDIO_SOURCE@")
        return result is not None and "MUTED" in result

    async def list_audio_devices(self) -> list:
        """List all PipeWire audio sinks and sources."""
        result = await self._run("wpctl status")
        if not result:
            return []

        devices = []
        current_type = None
        for line in result.splitlines():
            if "Sinks:" in line:
                current_type = "sink"
            elif "Sources:" in line:
                current_type = "source"
            elif current_type and "*" in line:
                # Default device
                match = re.search(r"(\d+)\.\s+(.+?)\s+\[", line)
                if match:
                    devices.append(AudioDevice(
                        device_id=match.group(1),
                        name=match.group(2).strip(),
                        device_type=current_type,
                        is_default=True,
                        volume_pct=await self.get_volume()
                        if current_type == "sink"
                        else await self.get_mic_volume(),
                        is_muted="MUTED" in line,
                    ))
        return devices

    # ── D-Bus / GNOME Shell ───────────────────────────────────

    async def get_active_window(self) -> str:
        """Get currently focused window title via xdotool or gdbus."""
        # Try xdotool (X11)
        result = await self._run(
            "xdotool getactivewindow getwindowname 2>/dev/null"
        )
        if result and result.strip():
            return result.strip()

        # Try gdbus (Wayland/GNOME)
        result = await self._run(
            "gdbus call --session --dest org.gnome.Shell "
            "--object-path /org/gnome/Shell "
            "--method org.gnome.Shell.Eval "
            "'global.display.focus_window?.title ?? \"\"'"
        )
        if result:
            match = re.search(r"'([^']+)'", result)
            if match:
                return match.group(1)

        return ""

    async def send_notification(
        self,
        title: str,
        body: str,
        urgency: str = "normal",
        icon: str = "dialog-information",
    ) -> bool:
        """
        Send desktop notification via notify-send.
        urgency: low | normal | critical
        """
        title_safe = title.replace('"', '\\"')[:80]
        body_safe = body.replace('"', '\\"')[:200]
        result = await self._run(
            f'notify-send --urgency={urgency} --icon={icon} '
            f'"{title_safe}" "{body_safe}"'
        )
        return result is not None

    async def get_gnome_setting(self, schema: str, key: str) -> Optional[str]:
        """Read a GNOME setting via gsettings."""
        result = await self._run(f"gsettings get {schema} {key}")
        return result.strip() if result else None

    async def set_gnome_setting(
        self, schema: str, key: str, value: str
    ) -> bool:
        """Write a GNOME setting via gsettings."""
        result = await self._run(f"gsettings set {schema} {key} {value}")
        return result is not None

    async def lock_screen(self) -> bool:
        """Lock the GNOME screen."""
        result = await self._run("loginctl lock-session")
        if result is None:
            result = await self._run(
                "gdbus call --session --dest org.gnome.ScreenSaver "
                "--object-path /org/gnome/ScreenSaver "
                "--method org.gnome.ScreenSaver.Lock"
            )
        return result is not None

    async def set_wallpaper(self, image_path: str) -> bool:
        """Set GNOME desktop wallpaper."""
        if not Path(image_path).exists():
            return False
        uri = f"file://{image_path}"
        result = await self._run(
            f"gsettings set org.gnome.desktop.background picture-uri '{uri}'"
        )
        return result is not None

    # ── System Metrics (/proc) ────────────────────────────────

    async def get_system_info(self) -> SystemInfo:
        """Collect comprehensive system snapshot."""
        cpu = await self._read_cpu_pct()
        ram_used, ram_total = await self._read_ram()
        uptime = await self._read_uptime()
        active_window = await self.get_active_window()
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
        sink_vol = await self.get_volume()
        mic_vol = await self.get_mic_volume()
        mic_muted_raw = await self._run(
            "wpctl get-volume @DEFAULT_AUDIO_SOURCE@"
        )
        mic_muted = mic_muted_raw is not None and "MUTED" in mic_muted_raw

        return SystemInfo(
            cpu_pct=cpu,
            ram_pct=round(ram_used / ram_total * 100, 1) if ram_total else 0.0,
            ram_used_gb=round(ram_used, 2),
            ram_total_gb=round(ram_total, 2),
            uptime_seconds=uptime,
            active_window=active_window,
            desktop_session=desktop,
            audio_sink_volume=sink_vol,
            mic_volume=mic_vol,
            is_mic_muted=mic_muted,
        )

    # ── udev / Hardware Events ────────────────────────────────

    async def list_usb_devices(self) -> list:
        """List connected USB devices via lsusb."""
        result = await self._run("lsusb")
        if not result:
            return []
        devices = []
        for line in result.strip().splitlines():
            match = re.match(
                r"Bus (\d+) Device (\d+): ID ([\w:]+) (.+)", line
            )
            if match:
                devices.append({
                    "bus": match.group(1),
                    "device": match.group(2),
                    "id": match.group(3),
                    "name": match.group(4).strip(),
                })
        return devices

    async def get_battery_status(self) -> dict:
        """Get battery status from /sys."""
        battery_path = Path("/sys/class/power_supply")
        for bat in battery_path.glob("BAT*"):
            try:
                capacity = int((bat / "capacity").read_text().strip())
                status = (bat / "status").read_text().strip()
                return {
                    "battery": bat.name,
                    "level_pct": capacity,
                    "status": status,
                    "charging": status == "Charging",
                }
            except Exception:
                pass
        return {"battery": None, "level_pct": None, "status": "not_found"}

    # ── Internal helpers ──────────────────────────────────────

    async def _run(self, cmd: str, timeout: float = 5.0) -> Optional[str]:
        """
        Run a shell command asynchronously.
        Returns stdout on success, None on failure.
        """
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                ),
                timeout=timeout,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            if proc.returncode == 0:
                return stdout.decode("utf-8", errors="replace")
            return None
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug(f"_run({cmd!r}) failed: {e}")
            return None

    async def _read_cpu_pct(self) -> float:
        """Read CPU usage from /proc/stat (two samples, 100ms apart)."""
        def _read_stat():
            try:
                line = Path("/proc/stat").read_text().splitlines()[0]
                vals = [int(x) for x in line.split()[1:]]
                idle = vals[3]
                total = sum(vals)
                return idle, total
            except Exception:
                return 0, 1

        idle1, total1 = _read_stat()
        await asyncio.sleep(0.1)
        idle2, total2 = _read_stat()

        diff_total = total2 - total1
        diff_idle = idle2 - idle1
        if diff_total == 0:
            return 0.0
        return round((1.0 - diff_idle / diff_total) * 100, 1)

    async def _read_ram(self) -> tuple:
        """Read RAM from /proc/meminfo. Returns (used_gb, total_gb)."""
        try:
            meminfo = Path("/proc/meminfo").read_text()
            total = int(re.search(r"MemTotal:\s+(\d+)", meminfo).group(1))
            available = int(
                re.search(r"MemAvailable:\s+(\d+)", meminfo).group(1)
            )
            used = total - available
            return used / 1024 / 1024, total / 1024 / 1024
        except Exception:
            return 0.0, 1.0

    async def _read_uptime(self) -> int:
        """Read system uptime in seconds from /proc/uptime."""
        try:
            content = Path("/proc/uptime").read_text()
            return int(float(content.split()[0]))
        except Exception:
            return 0
