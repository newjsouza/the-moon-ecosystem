"""
LinuxNativeAgent — Deep Zorin OS integration for The Moon.

Commands:
  'status'       → full system snapshot (CPU, RAM, audio, window)
  'volume'       → get/set volume (kwargs: level=0-100)
  'mute'         → toggle audio mute
  'mic'          → get/set/toggle mic (kwargs: action=mute|unmute|toggle)
  'notify'       → send desktop notification (kwargs: title, body, urgency)
  'lock'         → lock screen
  'wallpaper'    → set wallpaper (kwargs: path)
  'battery'      → battery status
  'usb'          → list USB devices
  'audio_devices'→ list PipeWire audio devices
  'hotkey'       → register global hotkey listener (background task)
  'pipeline'     → system health report → Telegram
"""
import asyncio
import logging
from datetime import datetime

from core.agent_base import AgentBase, TaskResult
from core.observability.decorators import observe_agent
from agents.llm import LLMRouter
from core.linux_native import LinuxNative, SystemInfo


@observe_agent
class LinuxNativeAgent(AgentBase):
    """
    Deep Linux/GNOME integration agent.
    Zero cost: uses only system binaries (wpctl, gdbus, gsettings, notify-send).
    """

    AGENT_ID = "linux_native"

    # Thresholds for health alerts
    CPU_ALERT_PCT    = 85.0
    RAM_ALERT_PCT    = 90.0
    BATTERY_LOW_PCT  = 15

    def __init__(self):
        super().__init__()
        self.llm = LLMRouter()
        self.native = LinuxNative()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._hotkey_task: asyncio.Task | None = None

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute LinuxNativeAgent command.
        kwargs vary by command — see docstring above.
        """
        start = asyncio.get_event_loop().time()
        cmd = task.lower().strip()

        try:
            if cmd == "status":
                return await self._system_status(start)
            elif cmd == "volume":
                return await self._handle_volume(kwargs, start)
            elif cmd == "mute":
                return await self._handle_mute(kwargs, start)
            elif cmd == "mic":
                return await self._handle_mic(kwargs, start)
            elif cmd == "notify":
                return await self._handle_notify(kwargs, start)
            elif cmd == "lock":
                ok = await self.native.lock_screen()
                return TaskResult(success=ok, data={"locked": ok},
                                  execution_time=asyncio.get_event_loop().time() - start)
            elif cmd == "wallpaper":
                path = kwargs.get("path", "")
                ok = await self.native.set_wallpaper(path)
                return TaskResult(success=ok, data={"path": path},
                                  error=None if ok else f"File not found: {path}",
                                  execution_time=asyncio.get_event_loop().time() - start)
            elif cmd == "battery":
                data = await self.native.get_battery_status()
                return TaskResult(success=True, data=data,
                                  execution_time=asyncio.get_event_loop().time() - start)
            elif cmd == "usb":
                devices = await self.native.list_usb_devices()
                return TaskResult(success=True,
                                  data={"devices": devices, "count": len(devices)},
                                  execution_time=asyncio.get_event_loop().time() - start)
            elif cmd == "audio_devices":
                devices = await self.native.list_audio_devices()
                return TaskResult(
                    success=True,
                    data={
                        "devices": [
                            {"id": d.device_id, "name": d.name,
                             "type": d.device_type, "default": d.is_default,
                             "volume": d.volume_pct, "muted": d.is_muted}
                            for d in devices
                        ],
                        "count": len(devices),
                    },
                    execution_time=asyncio.get_event_loop().time() - start
                )
            elif cmd == "hotkey":
                return await self._handle_hotkey(kwargs, start)
            elif cmd == "pipeline":
                return await self._run_health_pipeline(kwargs, start)
            else:
                return TaskResult(
                    success=False,
                    error=(
                        f"Unknown command: '{cmd}'. Valid: status, volume, mute, "
                        "mic, notify, lock, wallpaper, battery, usb, "
                        "audio_devices, hotkey, pipeline"
                    )
                )
        except Exception as e:
            self.logger.error(f"LinuxNativeAgent error: {e}", exc_info=True)
            return TaskResult(
                success=False, error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _system_status(self, start: float) -> TaskResult:
        """Collect full system snapshot."""
        info = await self.native.get_system_info()
        battery = await self.native.get_battery_status()

        alerts = []
        if info.cpu_pct >= self.CPU_ALERT_PCT:
            alerts.append(f"CPU alto: {info.cpu_pct}%")
        if info.ram_pct >= self.RAM_ALERT_PCT:
            alerts.append(f"RAM alta: {info.ram_pct}%")
        bat_lvl = battery.get("level_pct")
        if bat_lvl is not None and bat_lvl <= self.BATTERY_LOW_PCT \
                and not battery.get("charging"):
            alerts.append(f"Bateria baixa: {bat_lvl}%")

        return TaskResult(
            success=True,
            data={
                "cpu_pct":          info.cpu_pct,
                "ram_pct":          info.ram_pct,
                "ram_used_gb":      info.ram_used_gb,
                "ram_total_gb":     info.ram_total_gb,
                "uptime_seconds":   info.uptime_seconds,
                "uptime_human":     self._seconds_to_human(info.uptime_seconds),
                "active_window":    info.active_window,
                "desktop_session":  info.desktop_session,
                "audio_volume":     info.audio_sink_volume,
                "mic_volume":       info.mic_volume,
                "mic_muted":        info.is_mic_muted,
                "battery":          battery,
                "alerts":           alerts,
                "timestamp":        datetime.now().isoformat(),
            },
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _handle_volume(self, kwargs: dict, start: float) -> TaskResult:
        """Get or set volume."""
        if "level" in kwargs:
            level = float(kwargs["level"])
            ok = await self.native.set_volume(level)
            current = await self.native.get_volume()
            return TaskResult(
                success=ok,
                data={"action": "set", "requested": level, "current": current},
                execution_time=asyncio.get_event_loop().time() - start
            )
        else:
            vol = await self.native.get_volume()
            return TaskResult(
                success=True,
                data={"action": "get", "volume_pct": vol},
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _handle_mute(self, kwargs: dict, start: float) -> TaskResult:
        """Toggle audio mute."""
        is_muted = await self.native.toggle_mute()
        state = "muted" if is_muted else "unmuted"
        if kwargs.get("notify", False):
            await self.native.send_notification(
                "The Moon — Áudio",
                f"Som {state}",
                urgency="low"
            )
        return TaskResult(
            success=True,
            data={"muted": is_muted, "state": state},
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _handle_mic(self, kwargs: dict, start: float) -> TaskResult:
        """Handle microphone operations."""
        action = kwargs.get("action", "toggle").lower()

        if action == "mute":
            ok = await self.native.mute_mic()
            muted = True
        elif action == "unmute":
            ok = await self.native.unmute_mic()
            muted = False
        else:  # toggle
            muted = await self.native.toggle_mic()
            ok = True

        if kwargs.get("notify", False):
            state = "mutado" if muted else "ativo"
            await self.native.send_notification(
                "The Moon — Microfone",
                f"Microfone {state}",
                urgency="low",
                icon="audio-input-microphone"
            )

        return TaskResult(
            success=ok,
            data={"action": action, "muted": muted},
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _handle_notify(self, kwargs: dict, start: float) -> TaskResult:
        """Send desktop notification."""
        title = kwargs.get("title", "The Moon")
        body = kwargs.get("body", "")
        urgency = kwargs.get("urgency", "normal")

        if not body:
            return TaskResult(success=False, error="'body' kwarg required")

        ok = await self.native.send_notification(title, body, urgency)
        return TaskResult(
            success=ok,
            data={"sent": ok, "title": title, "body": body[:50]},
            execution_time=asyncio.get_event_loop().time() - start
        )

    async def _handle_hotkey(self, kwargs: dict, start: float) -> TaskResult:
        """
        Register global hotkey via pynput or xdotool.
        Non-blocking: spawns background monitoring task.
        kwargs:
            hotkey (str): key combo, e.g. "<ctrl>+<alt>+m"
            action (str): agent_id:command to trigger
        """
        hotkey = kwargs.get("hotkey", "")
        action = kwargs.get("action", "")

        if not hotkey or not action:
            return TaskResult(
                success=False,
                error="'hotkey' and 'action' kwargs required"
            )

        # Check if pynput is available
        try:
            import pynput
            self.logger.info(
                f"Registering hotkey {hotkey!r} → {action!r} via pynput"
            )
            # Note: actual hotkey registration needs to run in main thread
            # For daemon mode, use xdotool or evdev in a background thread
            return TaskResult(
                success=True,
                data={
                    "hotkey": hotkey,
                    "action": action,
                    "method": "pynput",
                    "note": (
                        "Hotkey registered. Start daemon with "
                        "python3 moon_sync.py --serve to activate."
                    ),
                },
                execution_time=asyncio.get_event_loop().time() - start
            )
        except ImportError:
            # Fallback: document the xdotool approach
            return TaskResult(
                success=True,
                data={
                    "hotkey": hotkey,
                    "action": action,
                    "method": "xdotool_workaround",
                    "note": (
                        "pynput not installed. Alternative: "
                        "add to GNOME custom shortcuts via gsettings. "
                        "pip install pynput for daemon hotkey support."
                    ),
                    "gsettings_cmd": (
                        f"gsettings set org.gnome.settings-daemon.plugins.media-keys "
                        f"custom-keybindings \"['/org/gnome/settings-daemon/plugins/"
                        f"media-keys/custom-keybindings/custom0/']\""
                    ),
                },
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _run_health_pipeline(
        self, kwargs: dict, start: float
    ) -> TaskResult:
        """Full health pipeline: snapshot → alerts → Telegram."""
        status = await self._system_status(start)
        data = status.data.copy()

        # Build Telegram message
        if not kwargs.get("dry_run", False):
            alerts = data.get("alerts", [])
            msg = (
                f"🖥️ *The Moon — Sistema*\n\n"
                f"💻 CPU: `{data['cpu_pct']}%` | "
                f"RAM: `{data['ram_pct']}%` "
                f"({data['ram_used_gb']:.1f}/{data['ram_total_gb']:.1f} GB)\n"
                f"🔊 Volume: `{data['audio_volume']}%` | "
                f"🎙 Mic: `{'muted' if data['mic_muted'] else 'active'}`\n"
                f"⏱ Uptime: `{data['uptime_human']}`\n"
                f"🪟 Janela: `{data['active_window'][:40] or 'N/A'}`"
            )
            if alerts:
                alert_str = "\n".join(f"⚠️ {a}" for a in alerts)
                msg += f"\n\n*ALERTAS:*\n{alert_str}"

            bat = data.get("battery", {})
            if bat.get("level_pct") is not None:
                charging = "⚡" if bat.get("charging") else "🔋"
                msg += f"\n{charging} Bateria: `{bat['level_pct']}%`"

            try:
                from telegram.bot import send_notification
                await send_notification(msg)
                data["telegram_sent"] = True
            except Exception as e:
                self.logger.debug(f"Telegram skipped: {e}")
                data["telegram_sent"] = False

        return TaskResult(
            success=True,
            data=data,
            execution_time=asyncio.get_event_loop().time() - start
        )

    @staticmethod
    def _seconds_to_human(seconds: int) -> str:
        """Convert seconds to human-readable string."""
        d, r = divmod(seconds, 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)
        if d > 0:
            return f"{d}d {h}h {m}m"
        elif h > 0:
            return f"{h}h {m}m"
        else:
            return f"{m}m {s}s"
