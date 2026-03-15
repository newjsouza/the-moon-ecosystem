"""
agents/hardware_synergy_bridge.py
Hardware Synergy Bridge — Agente Nativo OS do Ecossistema The Moon.

Integra profundamente com Zorin OS (PipeWire / D-Bus / Udev) para
transformar o ecossistema em uma presença física e inteligente.

FUNCIONALIDADES:
  - Captura de voz por hotkey global (Ctrl+Space) via push-to-talk
  - Transcrição via Groq Whisper (free tier)
  - Overlay GTK3 flutuante com 5 estados visuais de feedback
  - D-Bus: monitora bateria, rede, sessão (lock/unlock), screensaver
  - Udev: detecta periféricos USB (headphones, mouses, teclados)
  - Reações automáticas: ajuste de volume, alertas de bateria, pausas
  - Controle de áudio nativo via PipeWire (wpctl)

VISUAL FEEDBACK (SEM ÁUDIO DE RESPOSTA):
  IDLE        → Ícone discreto no canto inferior direito
  RECORDING   → Indicador pulsante vermelho + "Ouvindo..."
  TRANSCRIBING→ Spinner + texto transcrito aparecendo
  THINKING    → Pensamento do agente em texto (cor âmbar)
  RESPONDING  → Resposta completa do agente em texto (cor verde)

ZERO CUSTO:
  - GTK3 nativo do Zorin OS (sem instalação extra)
  - Groq Whisper large-v3-turbo (free tier)
  - sounddevice / pyaudio (PipeWire-compatible)
  - dbus-python, pyudev (libs Linux gratuitas)

VARIÁVEIS DE AMBIENTE:
  GROQ_API_KEY  → já existente no ecossistema
  MOON_HOTKEY   → tecla de ativação (default: ctrl+space)
  MOON_MIC_DEVICE → índice do dispositivo de microfone (default: auto)
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import queue
import subprocess
import threading
import time
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.agent_base import AgentBase, AgentPriority, TaskResult

logger = logging.getLogger("moon.agents.hardware")

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000    # Hz — Whisper preferred
CHANNELS       = 1
CHUNK_FRAMES   = 1024
MAX_RECORD_S   = 30       # seconds max push-to-talk
OVERLAY_W      = 480
OVERLAY_H      = 160
OVERLAY_MARGIN = 24       # px from screen edge
BATTERY_WARN   = 20       # % threshold for low battery alert
BATTERY_CRIT   = 10       # % threshold for critical battery alert
AUDIO_DATA_DIR = Path("data/hardware_bridge")


# ─────────────────────────────────────────────────────────────
#  Overlay States
# ─────────────────────────────────────────────────────────────

class OverlayState(str, Enum):
    IDLE         = "idle"
    RECORDING    = "recording"
    TRANSCRIBING = "transcribing"
    THINKING     = "thinking"
    RESPONDING   = "responding"
    ALERT        = "alert"


@dataclass
class OverlayPayload:
    """Data passed to the overlay to update its display."""
    state:      OverlayState
    line1:      str = ""     # Primary text (transcription / thought / response)
    line2:      str = ""     # Secondary text (sub-info)
    progress:   float = 0.0  # 0.0–1.0 for progress bar (transcribing state)
    auto_hide_s: float = 0.0 # 0 = stay; >0 = auto-hide after N seconds


# ─────────────────────────────────────────────────────────────
#  GTK3 Visual Feedback Overlay
# ─────────────────────────────────────────────────────────────

class VisualFeedbackOverlay:
    """
    Floating GTK3 window with 5 visual states.
    Runs in a dedicated thread with its own GLib main loop.

    States:
      IDLE         → moon icon, semi-transparent, stays at bottom-right
      RECORDING    → pulsing red mic icon + "Ouvindo..."
      TRANSCRIBING → spinner + partial transcription text
      THINKING     → amber text showing agent reasoning steps
      RESPONDING   → green text with final agent response
      ALERT        → orange banner for system alerts (battery, etc.)
    """

    # CSS for all overlay states
    _CSS = b"""
    window {
        background-color: rgba(10, 10, 20, 0.88);
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.08);
    }
    #container {
        padding: 16px 20px;
    }
    #state-icon {
        font-size: 22px;
        margin-right: 10px;
    }
    #state-label {
        font-family: "JetBrains Mono", "Fira Code", monospace;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 2px;
    }
    #line1 {
        font-family: "Inter", "Noto Sans", sans-serif;
        font-size: 14px;
        font-weight: 400;
        margin-top: 8px;
        color: rgba(255,255,255,0.92);
    }
    #line2 {
        font-family: "Inter", "Noto Sans", sans-serif;
        font-size: 11px;
        color: rgba(255,255,255,0.45);
        margin-top: 4px;
    }
    .state-idle         { color: rgba(120,160,255,0.7); }
    .state-recording    { color: #ff4466; }
    .state-transcribing { color: #66bbff; }
    .state-thinking     { color: #ffaa33; }
    .state-responding   { color: #44ff99; }
    .state-alert        { color: #ff8833; }
    progressbar trough  { background-color: rgba(255,255,255,0.12); min-height: 3px; border-radius: 2px; }
    progressbar progress{ background-color: #66bbff; border-radius: 2px; }
    """

    _STATE_META: Dict[OverlayState, Dict] = {
        OverlayState.IDLE:         {"icon": "🌙", "label": "THE MOON",   "css_class": "state-idle"},
        OverlayState.RECORDING:    {"icon": "🎙️", "label": "OUVINDO",    "css_class": "state-recording"},
        OverlayState.TRANSCRIBING: {"icon": "✍️",  "label": "TRADUZINDO", "css_class": "state-transcribing"},
        OverlayState.THINKING:     {"icon": "🧠", "label": "PENSANDO",   "css_class": "state-thinking"},
        OverlayState.RESPONDING:   {"icon": "💬", "label": "RESPOSTA",   "css_class": "state-responding"},
        OverlayState.ALERT:        {"icon": "⚠️",  "label": "ALERTA",    "css_class": "state-alert"},
    }

    def __init__(self) -> None:
        self._gtk_available = False
        self._window        = None
        self._thread: Optional[threading.Thread] = None
        self._update_queue: queue.Queue[Optional[OverlayPayload]] = queue.Queue()
        self._running = False
        self._pulse_timer_id = None

    def start(self) -> bool:
        """Starts the overlay in a background thread. Returns True if GTK is available."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk  # noqa
            self._gtk_available = True
        except Exception as exc:
            logger.warning(f"GTK3 not available — overlay disabled: {exc}")
            return False

        self._running = True
        self._thread  = threading.Thread(
            target=self._gtk_main, daemon=True, name="moon.overlay.gtk"
        )
        self._thread.start()
        time.sleep(0.3)  # let GTK initialize
        return True

    def stop(self) -> None:
        """Signals the GTK loop to quit."""
        self._running = False
        self._update_queue.put(None)  # sentinel
        if self._gtk_available:
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                from gi.repository import GLib
                GLib.idle_add(self._quit_gtk)
            except Exception:
                pass

    def update(self, payload: OverlayPayload) -> None:
        """Thread-safe update: enqueue payload, GTK loop applies it."""
        if self._gtk_available and self._running:
            self._update_queue.put(payload)
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                from gi.repository import GLib
                GLib.idle_add(self._apply_pending_updates)
            except Exception:
                pass
        else:
            # Fallback: print to terminal
            meta = self._STATE_META.get(payload.state, {})
            icon = meta.get("icon", "•")
            label = meta.get("label", payload.state.value.upper())
            if payload.line1:
                logger.info(f"[OVERLAY] {icon} {label} | {payload.line1}")
            if payload.line2:
                logger.info(f"[OVERLAY]    └ {payload.line2}")

    # ── GTK Thread ──────────────────────────────────────────

    def _gtk_main(self) -> None:
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gdk, GLib, GObject

            # Build window
            win = Gtk.Window(type=Gtk.WindowType.POPUP)
            win.set_app_paintable(True)
            win.set_keep_above(True)
            win.set_decorated(False)
            win.set_skip_taskbar_hint(True)
            win.set_skip_pager_hint(True)
            win.set_default_size(OVERLAY_W, OVERLAY_H)

            # Enable RGBA / transparency
            screen  = win.get_screen()
            visual  = screen.get_rgba_visual()
            if visual:
                win.set_visual(visual)

            # CSS
            css_prov = Gtk.CssProvider()
            css_prov.load_from_data(self._CSS)
            Gtk.StyleContext.add_provider_for_screen(
                screen, css_prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

            # Position: bottom-right corner
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            if monitor:
                geom = monitor.get_geometry()
                win.move(
                    geom.x + geom.width  - OVERLAY_W - OVERLAY_MARGIN,
                    geom.y + geom.height - OVERLAY_H - OVERLAY_MARGIN,
                )
            else:
                # Absolute fallback
                win.move(100, 100)

            # Layout
            container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            container.set_name("container")

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            icon_label = Gtk.Label(label="🌙")
            icon_label.set_name("state-icon")
            state_label = Gtk.Label(label="THE MOON")
            state_label.set_name("state-label")
            header.pack_start(icon_label, False, False, 0)
            header.pack_start(state_label, False, False, 0)
            container.pack_start(header, False, False, 0)

            line1_label = Gtk.Label(label="")
            line1_label.set_name("line1")
            line1_label.set_line_wrap(True)
            line1_label.set_max_width_chars(48)
            line1_label.set_xalign(0.0)
            container.pack_start(line1_label, False, False, 0)

            line2_label = Gtk.Label(label="")
            line2_label.set_name("line2")
            line2_label.set_xalign(0.0)
            container.pack_start(line2_label, False, False, 0)

            progress_bar = Gtk.ProgressBar()
            progress_bar.set_fraction(0.0)
            container.pack_start(progress_bar, False, False, 4)

            win.add(container)

            self._window     = win
            self._icon_label  = icon_label
            self._state_label = state_label
            self._line1_label = line1_label
            self._line2_label = line2_label
            self._progress    = progress_bar
            self._gtk_mod     = (Gtk, Gdk, GLib, GObject)

            win.show_all()
            progress_bar.hide()

            # Idle checker for updates
            GLib.timeout_add(50, self._apply_pending_updates)

            # Pulse animation for RECORDING state
            GLib.timeout_add(600, self._pulse_tick)

            Gtk.main()

        except Exception as exc:
            logger.error(f"GTK overlay thread error: {exc}")

    def _apply_pending_updates(self) -> bool:
        """Called from GLib main loop — drains the update queue."""
        try:
            while True:
                payload = self._update_queue.get_nowait()
                if payload is None:
                    return False  # stop idle
                self._apply_update(payload)
        except queue.Empty:
            pass
        return True  # keep idle callback alive

    def _apply_update(self, payload: OverlayPayload) -> None:
        if not self._window:
            return
        try:
            Gtk, Gdk, GLib, _ = self._gtk_mod
            meta = self._STATE_META.get(payload.state, {})

            # Update state icon and label
            self._icon_label.set_text(meta.get("icon", "•"))
            self._state_label.set_text(meta.get("label", ""))

            # Update CSS class on state_label
            ctx = self._state_label.get_style_context()
            for s in self._STATE_META.values():
                ctx.remove_class(s["css_class"])
            ctx.add_class(meta.get("css_class", "state-idle"))

            # Update text lines
            self._line1_label.set_text(payload.line1[:200] if payload.line1 else "")
            self._line2_label.set_text(payload.line2[:100] if payload.line2 else "")

            # Progress bar
            if payload.state == OverlayState.TRANSCRIBING and payload.progress > 0:
                self._progress.show()
                self._progress.set_fraction(min(1.0, payload.progress))
            else:
                self._progress.hide()

            # Resize window to content
            self._window.resize(OVERLAY_W, 1)

            # Auto-hide
            if payload.auto_hide_s > 0:
                GLib.timeout_add(
                    int(payload.auto_hide_s * 1000),
                    lambda: self._go_idle()
                )

        except Exception as exc:
            logger.warning(f"Overlay update error: {exc}")

    def _pulse_tick(self) -> bool:
        """Animates opacity for RECORDING state."""
        if not self._window:
            return False
        try:
            Gtk, _, _, _ = self._gtk_mod
            ctx = self._state_label.get_style_context()
            if ctx.has_class("state-recording"):
                current = self._window.get_opacity()
                self._window.set_opacity(0.7 if current > 0.85 else 1.0)
        except Exception:
            pass
        return True  # keep ticking

    def _go_idle(self) -> None:
        self._apply_update(OverlayPayload(state=OverlayState.IDLE))

    def _quit_gtk(self) -> None:
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
            if self._window:
                self._window.destroy()
            Gtk.main_quit()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  Audio Capture (PipeWire-compatible via sounddevice)
# ─────────────────────────────────────────────────────────────

class AudioCapture:
    """
    Push-to-talk audio capture via sounddevice (PipeWire backend).
    Writes WAV to a BytesIO buffer ready for Whisper.
    """

    def __init__(self, device_index: Optional[int] = None) -> None:
        self._device   = device_index
        self._frames:  List[bytes] = []
        self._recording = False
        self._lock      = threading.Lock()

    def start_recording(self) -> None:
        with self._lock:
            self._frames    = []
            self._recording = True

    def stop_recording(self) -> Optional[bytes]:
        """Stops recording and returns WAV bytes, or None if no audio."""
        with self._lock:
            self._recording = False
            frames = self._frames.copy()

        if not frames:
            return None

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)   # 16-bit PCM
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    async def record_until_stop(self, stop_event: asyncio.Event) -> Optional[bytes]:
        """
        Records in a thread-pool executor until stop_event is set or MAX_RECORD_S.
        Returns WAV bytes.
        """
        loop = asyncio.get_event_loop()
        self.start_recording()

        def _record_thread() -> None:
            try:
                import sounddevice as sd
                import numpy as np

                def _callback(indata, frames_count, time_info, status):
                    if status:
                        logger.debug(f"Audio stream status: {status}")
                    with self._lock:
                        if self._recording:
                            self._frames.append(bytes(indata))

                kwargs: Dict[str, Any] = {
                    "samplerate": SAMPLE_RATE,
                    "channels":   CHANNELS,
                    "dtype":      "int16",
                    "callback":   _callback,
                }
                if self._device is not None:
                    kwargs["device"] = self._device

                with sd.InputStream(**kwargs):
                    start = time.monotonic()
                    while self._recording:
                        time.sleep(0.05)
                        if time.monotonic() - start >= MAX_RECORD_S:
                            break

            except ImportError:
                logger.error("sounddevice not installed. Run: pip install sounddevice")
            except Exception as exc:
                logger.error(f"Audio recording error: {exc}")

        # Run in thread so we don't block the event loop
        thread = threading.Thread(target=_record_thread, daemon=True)
        thread.start()

        # Wait for stop event
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=MAX_RECORD_S)
        except asyncio.TimeoutError:
            pass

        return self.stop_recording()

    @staticmethod
    def list_devices() -> List[Dict]:
        """Returns available input devices."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            return [
                {"index": i, "name": d["name"], "channels": d["max_input_channels"]}
                for i, d in enumerate(devices)
                if d["max_input_channels"] > 0
            ]
        except ImportError:
            return []


# ─────────────────────────────────────────────────────────────
#  Groq Whisper Transcriber
# ─────────────────────────────────────────────────────────────

class WhisperTranscriber:
    """
    Transcribes WAV audio bytes via Groq Whisper (free tier).
    Uses whisper-large-v3-turbo — best speed/quality ratio on Groq.
    """

    def __init__(self, groq_client) -> None:
        self._groq = groq_client

    async def transcribe(self, wav_bytes: bytes) -> Optional[str]:
        if not self._groq or not wav_bytes:
            return None
        try:
            # Groq audio transcription API
            import io as _io
            audio_file = _io.BytesIO(wav_bytes)
            audio_file.name = "audio.wav"

            loop = asyncio.get_event_loop()
            # Groq transcription is sync — run in executor
            result = await loop.run_in_executor(
                None,
                lambda: self._groq.audio.transcriptions.create(
                    model    = "whisper-large-v3-turbo",
                    file     = audio_file,
                    language = "pt",   # Portuguese — adjust via env var if needed
                ),
            )
            text = result.text.strip()
            logger.info(f"Whisper transcribed: '{text[:80]}'")
            return text if text else None

        except Exception as exc:
            logger.error(f"Whisper transcription failed: {exc}")
            return None


# ─────────────────────────────────────────────────────────────
#  Global Hotkey Listener (Linux evdev — no root required)
# ─────────────────────────────────────────────────────────────

class HotkeyListener:
    """
    Listens for a global hotkey using the `keyboard` library.
    Falls back to evdev if `keyboard` is unavailable.
    Hotkey: Ctrl+Space (configurable via MOON_HOTKEY env var).
    """

    def __init__(self, on_press: Callable, on_release: Callable) -> None:
        self._on_press   = on_press
        self._on_release = on_release
        self._hotkey     = os.getenv("MOON_HOTKEY", "ctrl+space")
        self._thread: Optional[threading.Thread] = None
        self._running    = False
        self._backend    = "none"

    def start(self) -> bool:
        """Returns True if a hotkey backend was found."""
        try:
            import keyboard as kb
            self._backend = "keyboard"
            self._running = True
            self._thread = threading.Thread(
                target=self._listen_keyboard, daemon=True,
                name="moon.hotkey.listener"
            )
            self._thread.start()
            logger.info(f"HotkeyListener started (keyboard backend) — hotkey: {self._hotkey}")
            return True
        except ImportError:
            pass

        # Fallback: notify user and run a simple stdin listener for testing
        logger.warning(
            "HotkeyListener: 'keyboard' library not available. "
            "Install with: pip install keyboard --break-system-packages\n"
            "Falling back to stdin trigger (type 'rec' + Enter to record)."
        )
        self._backend = "stdin"
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_stdin, daemon=True,
            name="moon.hotkey.stdin"
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._backend == "keyboard":
            try:
                import keyboard as kb
                kb.unhook_all()
            except Exception:
                pass

    def _listen_keyboard(self) -> None:
        try:
            import keyboard as kb
            kb.add_hotkey(self._hotkey, self._on_press)
            kb.add_hotkey(
                self._hotkey, self._on_release, trigger_on_release=True
            )
            while self._running:
                time.sleep(0.1)
        except Exception as exc:
            logger.error(f"Hotkey listener error: {exc}")

    def _listen_stdin(self) -> None:
        """Stdin fallback: 'rec' to start, any key to stop."""
        while self._running:
            try:
                cmd = input().strip().lower()
                if cmd == "rec":
                    self._on_press()
                    input()  # wait for Enter to stop
                    self._on_release()
            except EOFError:
                break
            except Exception:
                time.sleep(0.1)


# ─────────────────────────────────────────────────────────────
#  D-Bus System Event Listener
# ─────────────────────────────────────────────────────────────

class DBusEventListener:
    """
    Subscribes to D-Bus signals for system events:
      - UPower: battery level changes
      - NetworkManager: connectivity changes
      - GNOME ScreenSaver: screen lock/unlock
      - logind: session active/inactive
    """

    def __init__(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        self._callback = callback
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._available = False

    def start(self) -> bool:
        try:
            import dbus
            import dbus.mainloop.glib
            self._available = True
        except ImportError:
            logger.warning("dbus-python not available — D-Bus monitoring disabled.")
            return False

        self._running = True
        self._thread  = threading.Thread(
            target=self._dbus_main, daemon=True, name="moon.dbus.listener"
        )
        self._thread.start()
        logger.info("D-Bus event listener started.")
        return True

    def stop(self) -> None:
        self._running = False

    def _dbus_main(self) -> None:
        try:
            import dbus
            import dbus.mainloop.glib
            from gi.repository import GLib

            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus  = dbus.SystemBus()
            loop = GLib.MainLoop()

            # ── UPower: battery ─────────────────────────────
            try:
                bus.add_signal_receiver(
                    self._on_battery_changed,
                    dbus_interface = "org.freedesktop.DBus.Properties",
                    signal_name    = "PropertiesChanged",
                    path           = "/org/freedesktop/UPower/devices/battery_BAT0",
                )
            except Exception as exc:
                logger.debug(f"UPower signal: {exc}")

            # ── NetworkManager: connectivity ─────────────────
            try:
                bus.add_signal_receiver(
                    self._on_network_changed,
                    dbus_interface = "org.freedesktop.NetworkManager",
                    signal_name    = "StateChanged",
                )
            except Exception as exc:
                logger.debug(f"NetworkManager signal: {exc}")

            # ── GNOME ScreenSaver: lock/unlock ───────────────
            try:
                session_bus = dbus.SessionBus()
                session_bus.add_signal_receiver(
                    self._on_screensaver,
                    dbus_interface = "org.gnome.ScreenSaver",
                    signal_name    = "ActiveChanged",
                )
            except Exception as exc:
                logger.debug(f"ScreenSaver signal: {exc}")

            loop.run()

        except Exception as exc:
            logger.error(f"D-Bus main loop error: {exc}")

    def _on_battery_changed(self, interface, changed, invalidated) -> None:
        try:
            if "Percentage" in changed:
                pct = float(changed["Percentage"])
                self._callback("battery", {"percent": pct})
        except Exception:
            pass

    def _on_network_changed(self, state) -> None:
        # NM states: 70=connected, 20=disconnected
        connected = int(state) >= 70
        self._callback("network", {"connected": connected, "state": int(state)})

    def _on_screensaver(self, active) -> None:
        self._callback("screensaver", {"locked": bool(active)})


# ─────────────────────────────────────────────────────────────
#  Udev Peripheral Monitor
# ─────────────────────────────────────────────────────────────

class UdevPeripheralMonitor:
    """
    Monitors USB device events via pyudev.
    Detects: headphones, mice, keyboards, USB drives, webcams.
    """

    _DEVICE_PATTERNS = {
        "audio":    ["headphone", "headset", "speaker", "audio", "usb audio"],
        "input":    ["mouse", "keyboard", "gamepad", "joystick"],
        "storage":  ["flash drive", "usb drive", "mass storage"],
        "video":    ["webcam", "camera", "video"],
    }

    def __init__(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        self._callback = callback
        self._thread: Optional[threading.Thread] = None
        self._running  = False

    def start(self) -> bool:
        try:
            import pyudev
        except ImportError:
            logger.warning("pyudev not available — Udev monitoring disabled.")
            return False

        self._running = True
        self._thread  = threading.Thread(
            target=self._monitor_loop, daemon=True, name="moon.udev.monitor"
        )
        self._thread.start()
        logger.info("Udev peripheral monitor started.")
        return True

    def stop(self) -> None:
        self._running = False

    def _monitor_loop(self) -> None:
        try:
            import pyudev
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by("usb")

            for device in iter(monitor):
                if not self._running:
                    break
                try:
                    action = device.action
                    name   = (
                        device.get("ID_MODEL", "") or
                        device.get("DEVNAME", "") or
                        "Unknown Device"
                    ).lower()
                    vendor = device.get("ID_VENDOR", "")
                    dtype  = self._classify_device(name)

                    self._callback("peripheral", {
                        "action":      action,      # "add" or "remove"
                        "device_name": name,
                        "device_type": dtype,
                        "vendor":      vendor,
                    })
                except Exception as exc:
                    logger.debug(f"Udev event processing error: {exc}")

        except Exception as exc:
            logger.error(f"Udev monitor error: {exc}")

    def _classify_device(self, name: str) -> str:
        for dtype, patterns in self._DEVICE_PATTERNS.items():
            if any(p in name for p in patterns):
                return dtype
        return "generic"


# ─────────────────────────────────────────────────────────────
#  PipeWire Audio Control (via wpctl shell commands)
# ─────────────────────────────────────────────────────────────

class PipeWireController:
    """
    Thin wrapper around wpctl for PipeWire audio control.
    All operations are fire-and-forget shell commands.
    """

    @staticmethod
    def set_volume(percent: int, device: str = "@DEFAULT_AUDIO_SINK@") -> bool:
        """Set volume (0–100%). Returns True on success."""
        try:
            pct = max(0, min(100, percent))
            subprocess.run(
                ["wpctl", "set-volume", device, f"{pct / 100:.2f}"],
                check=True, capture_output=True, timeout=3
            )
            return True
        except Exception as exc:
            logger.warning(f"wpctl set-volume failed: {exc}")
            return False

    @staticmethod
    def set_mute(muted: bool, device: str = "@DEFAULT_AUDIO_SINK@") -> bool:
        """Mute or unmute a device."""
        try:
            state = "1" if muted else "0"
            subprocess.run(
                ["wpctl", "set-mute", device, state],
                check=True, capture_output=True, timeout=3
            )
            return True
        except Exception as exc:
            logger.warning(f"wpctl set-mute failed: {exc}")
            return False

    @staticmethod
    def get_volume(device: str = "@DEFAULT_AUDIO_SINK@") -> Optional[float]:
        """Returns current volume (0.0–1.0) or None."""
        try:
            result = subprocess.run(
                ["wpctl", "get-volume", device],
                capture_output=True, text=True, timeout=3
            )
            # Output: "Volume: 0.75" or "Volume: 0.75 [MUTED]"
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                return float(parts[1])
        except Exception:
            pass
        return None

    @staticmethod
    def notify(title: str, body: str, icon: str = "dialog-information") -> None:
        """Send a desktop notification via notify-send as fallback."""
        try:
            subprocess.run(
                ["notify-send", "-i", icon, title, body],
                timeout=3, capture_output=True
            )
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  Hardware Synergy Bridge — Main Agent
# ─────────────────────────────────────────────────────────────

class HardwareSynergyBridge(AgentBase):
    """
    Hardware Synergy Bridge — Agente Nativo OS do The Moon.

    Integra o ecossistema com o Zorin OS via PipeWire, D-Bus e Udev.
    Oferece interface de voz com feedback visual (sem resposta em áudio).

    FLUXO DE VOZ:
      1. Usuário pressiona Ctrl+Space → overlay muda para RECORDING
      2. Mic captura áudio (PipeWire/sounddevice)
      3. Solta Ctrl+Space → overlay muda para TRANSCRIBING
      4. Groq Whisper transcreve → overlay mostra texto transcrito
      5. Orchestrator processa → overlay mostra THINKING com raciocínio
      6. Resposta chega → overlay mostra RESPONDING com texto completo
      7. Após 8s → overlay volta para IDLE

    Public actions (via execute):
      speak        → Process text as if it were a voice command
      volume       → Set/get system volume (kwargs: action, value, device)
      mute         → Mute/unmute (kwargs: muted, device)
      notify       → Send desktop notification (kwargs: title, body)
      status       → Hardware and overlay status snapshot
      list_devices → List available microphone devices
    """

    def __init__(self, groq_client=None, message_bus=None, orchestrator=None) -> None:
        super().__init__()
        self.name        = "HardwareSynergyBridge"
        self.description = (
            "Native OS agent: voice input, visual feedback overlay, "
            "system event monitoring (battery, network, peripherals)."
        )
        self.priority = AgentPriority.HIGH

        # ── Dependencies ─────────────────────────────────────────
        self._groq        = groq_client
        self._message_bus = message_bus
        self._orchestrator = orchestrator

        # ── Subsystems ───────────────────────────────────────────
        self._overlay    = VisualFeedbackOverlay()
        self._audio      = AudioCapture(
            device_index=_int_env("MOON_MIC_DEVICE", None)
        )
        self._transcriber = WhisperTranscriber(groq_client)
        self._hotkey     = HotkeyListener(
            on_press   = self._on_hotkey_press,
            on_release = self._on_hotkey_release,
        )
        self._dbus       = DBusEventListener(self._on_system_event)
        self._udev       = UdevPeripheralMonitor(self._on_system_event)
        self._pipewire   = PipeWireController()

        # ── Voice pipeline state ─────────────────────────────────
        self._recording_event = asyncio.Event()
        self._is_recording    = False
        self._voice_task: Optional[asyncio.Task] = None

        # ── Battery state ────────────────────────────────────────
        self._last_battery_pct  = 100.0
        self._battery_warned_20 = False
        self._battery_warned_10 = False

        # ── Loop control ─────────────────────────────────────────
        self._stop_event = asyncio.Event()

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        AUDIO_DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Start visual overlay (non-fatal)
        if not self._overlay.start():
            logger.warning("Visual overlay unavailable — terminal fallback active.")

        # Start system event listeners (non-fatal each)
        self._dbus.start()
        self._udev.start()

        # Start hotkey listener
        self._hotkey.start()

        self._stop_event.clear()

        # Show idle state
        self._overlay.update(OverlayPayload(
            state=OverlayState.IDLE,
            line2="Pressione Ctrl+Space para falar",
        ))

        logger.info(f"{self.name} initialized — Jarvis mode active.")

    async def shutdown(self) -> None:
        self._stop_event.set()

        if self._voice_task and not self._voice_task.done():
            self._voice_task.cancel()
            try:
                await self._voice_task
            except asyncio.CancelledError:
                pass

        self._hotkey.stop()
        self._dbus.stop()
        self._udev.stop()
        self._overlay.stop()

        await super().shutdown()
        logger.info(f"{self.name} shut down.")

    async def ping(self) -> bool:
        return not self._stop_event.is_set()

    # ═══════════════════════════════════════════════════════════
    #  Execute Dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, action: str, **kwargs: Any) -> TaskResult:
        match action:
            case "speak":
                text = kwargs.get("text", "")
                if not text:
                    return TaskResult(success=False, error="'text' is required.")
                return await self._process_voice_input(text)

            case "volume":
                return self._handle_volume(kwargs)

            case "mute":
                muted  = bool(kwargs.get("muted", True))
                device = kwargs.get("device", "@DEFAULT_AUDIO_SINK@")
                ok     = self._pipewire.set_mute(muted, device)
                return TaskResult(success=ok, data={"muted": muted, "device": device})

            case "notify":
                title = kwargs.get("title", "The Moon")
                body  = kwargs.get("body", "")
                icon  = kwargs.get("icon", "dialog-information")
                self._pipewire.notify(title, body, icon)
                return TaskResult(success=True, data={"notified": True})

            case "status":
                return TaskResult(success=True, data=self._get_status())

            case "list_devices":
                devices = AudioCapture.list_devices()
                return TaskResult(success=True, data={"devices": devices})

            case _:
                return TaskResult(success=False, error=f"Unknown action: '{action}'")

    # ═══════════════════════════════════════════════════════════
    #  Hotkey Handlers (called from non-async hotkey thread)
    # ═══════════════════════════════════════════════════════════

    def _on_hotkey_press(self) -> None:
        """Called when Ctrl+Space is pressed — starts recording."""
        if self._is_recording:
            return
        self._is_recording = True
        self._recording_event.clear()

        # Schedule the async voice pipeline in the event loop
        try:
            loop = asyncio.get_event_loop()
            self._voice_task = loop.create_task(
                self._voice_pipeline(), name="moon.hardware.voice"
            )
        except RuntimeError:
            # If called from a thread without a running loop
            pass

    def _on_hotkey_release(self) -> None:
        """Called when Ctrl+Space is released — stops recording."""
        if self._is_recording:
            self._recording_event.set()

    # ═══════════════════════════════════════════════════════════
    #  Voice Pipeline (the core flow)
    # ═══════════════════════════════════════════════════════════

    async def _voice_pipeline(self) -> None:
        """
        Full voice input → processing → visual feedback pipeline.

        Steps:
          1. RECORDING  — show pulsing overlay, capture mic
          2. TRANSCRIBING — show spinner + partial text
          3. THINKING   — show agent reasoning (intermediate steps)
          4. RESPONDING — show final response text
          5. IDLE       — auto-hide after 8s
        """
        try:
            # ── Step 1: RECORDING ────────────────────────────────
            self._overlay.update(OverlayPayload(
                state = OverlayState.RECORDING,
                line1 = "Ouvindo... (solte Ctrl+Space para enviar)",
                line2 = f"Máx {MAX_RECORD_S}s",
            ))

            wav_bytes = await self._audio.record_until_stop(self._recording_event)

            if not wav_bytes:
                self._overlay.update(OverlayPayload(
                    state=OverlayState.IDLE, line2="Nenhum áudio capturado.",
                    auto_hide_s=3.0,
                ))
                self._is_recording = False
                return

            # ── Step 2: TRANSCRIBING ─────────────────────────────
            self._overlay.update(OverlayPayload(
                state    = OverlayState.TRANSCRIBING,
                line1    = "Transcrevendo...",
                progress = 0.3,
            ))

            transcribed = await self._transcriber.transcribe(wav_bytes)

            if not transcribed:
                self._overlay.update(OverlayPayload(
                    state=OverlayState.ALERT,
                    line1="Não entendi. Tente novamente.",
                    auto_hide_s=4.0,
                ))
                self._is_recording = False
                return

            self._overlay.update(OverlayPayload(
                state    = OverlayState.TRANSCRIBING,
                line1    = f'"{transcribed}"',
                line2    = "Processando...",
                progress = 0.7,
            ))

            # ── Steps 3 & 4: Process with Orchestrator ───────────
            await self._process_voice_input(transcribed)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Voice pipeline error: {exc}")
            self._overlay.update(OverlayPayload(
                state=OverlayState.ALERT,
                line1=f"Erro: {str(exc)[:100]}",
                auto_hide_s=5.0,
            ))
        finally:
            self._is_recording = False

    async def _process_voice_input(self, text: str) -> TaskResult:
        """
        Sends transcribed text to the Orchestrator and streams the
        response back to the visual overlay with thinking + response.
        """
        # ── THINKING step ────────────────────────────────────────
        self._overlay.update(OverlayPayload(
            state = OverlayState.THINKING,
            line1 = f"🧠 Analisando: \"{text[:80]}\"",
            line2 = "Consultando agentes...",
        ))

        response_text = "Orchestrator não disponível."
        success       = False

        try:
            if self._orchestrator:
                # Attempt to route through Orchestrator
                result = await asyncio.wait_for(
                    self._orchestrator._route_command(
                        text,
                        {"source": self.name, "input_type": "voice"},
                    ),
                    timeout=30,
                )
                response_text = result if isinstance(result, str) else str(result)
                success = True

            elif self._groq:
                # Direct Groq fallback if no orchestrator
                resp = await self._groq.chat.completions.create(
                    model    = "llama-3.1-8b-instant",
                    messages = [{"role": "user", "content": text}],
                    max_tokens=512,
                )
                response_text = resp.choices[0].message.content.strip()
                success = True

        except asyncio.TimeoutError:
            response_text = "⏱️ Tempo limite excedido. Tente novamente."
        except Exception as exc:
            response_text = f"Erro ao processar: {str(exc)[:100]}"
            logger.error(f"Voice input processing error: {exc}")

        # ── RESPONDING step ──────────────────────────────────────
        # Truncate for overlay display (show first 300 chars)
        display_text = response_text[:300]
        if len(response_text) > 300:
            display_text += "..."

        self._overlay.update(OverlayPayload(
            state       = OverlayState.RESPONDING,
            line1       = display_text,
            line2       = f"({len(response_text)} chars) | Entrada: \"{text[:40]}\"",
            auto_hide_s = 8.0,
        ))

        # Publish to MessageBus for logging/memory
        if self._message_bus:
            asyncio.create_task(
                self._message_bus.publish(
                    sender  = self.name,
                    topic   = "voice.interaction",
                    payload = {
                        "input":     text,
                        "response":  response_text,
                        "success":   success,
                        "timestamp": time.time(),
                    },
                    target  = "SemanticMemoryWeaver",
                )
            )

        return TaskResult(
            success=success,
            data={"input": text, "response": response_text},
        )

    # ═══════════════════════════════════════════════════════════
    #  System Event Reactions (D-Bus + Udev callbacks)
    # ═══════════════════════════════════════════════════════════

    def _on_system_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Receives system events from D-Bus and Udev listeners.
        Schedules async reactions in the event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                asyncio.create_task,
                self._react_to_event(event_type, data),
            )
        except Exception as exc:
            logger.debug(f"Event scheduling error: {exc}")

    async def _react_to_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Reacts intelligently to system events."""
        match event_type:
            case "battery":
                await self._handle_battery_event(data)
            case "network":
                await self._handle_network_event(data)
            case "screensaver":
                await self._handle_screensaver_event(data)
            case "peripheral":
                await self._handle_peripheral_event(data)

    async def _handle_battery_event(self, data: Dict) -> None:
        pct = data.get("percent", 100.0)
        self._last_battery_pct = pct

        if pct <= BATTERY_CRIT and not self._battery_warned_10:
            self._battery_warned_10 = True
            self._overlay.update(OverlayPayload(
                state=OverlayState.ALERT,
                line1=f"🔴 Bateria CRÍTICA: {pct:.0f}%",
                line2="Conecte o carregador imediatamente.",
                auto_hide_s=15.0,
            ))
            self._pipewire.notify(
                "⚠️ Bateria Crítica",
                f"Nível em {pct:.0f}%. Conecte o carregador.",
                "battery-caution"
            )

        elif pct <= BATTERY_WARN and not self._battery_warned_20:
            self._battery_warned_20 = True
            self._overlay.update(OverlayPayload(
                state=OverlayState.ALERT,
                line1=f"🟡 Bateria baixa: {pct:.0f}%",
                line2="Considere conectar o carregador.",
                auto_hide_s=8.0,
            ))

        elif pct > BATTERY_WARN + 5:
            # Reset warnings when battery recovers
            self._battery_warned_20 = False
            self._battery_warned_10 = False

    async def _handle_network_event(self, data: Dict) -> None:
        connected = data.get("connected", True)
        if not connected:
            self._overlay.update(OverlayPayload(
                state=OverlayState.ALERT,
                line1="📡 Conexão de rede perdida",
                line2="Agentes de pesquisa pausados.",
                auto_hide_s=6.0,
            ))
        else:
            self._overlay.update(OverlayPayload(
                state=OverlayState.IDLE,
                line1="✅ Rede reconectada",
                line2="Agentes de pesquisa retomando.",
                auto_hide_s=4.0,
            ))

    async def _handle_screensaver_event(self, data: Dict) -> None:
        locked = data.get("locked", False)
        if locked:
            logger.info("Screen locked — low-power mode hint.")
            # Could signal Orchestrator to pause non-critical proactive tasks
            if self._message_bus:
                asyncio.create_task(self._message_bus.publish(
                    sender  = self.name,
                    topic   = "system.screen_locked",
                    payload = {"locked": True, "timestamp": time.time()},
                    target  = "orchestrator",
                ))

    async def _handle_peripheral_event(self, data: Dict) -> None:
        action      = data.get("action", "")
        device_name = data.get("device_name", "dispositivo")
        device_type = data.get("device_type", "generic")

        if action == "add":
            # Headphones/audio device connected → lower volume to safe level
            if device_type == "audio":
                current_vol = self._pipewire.get_volume()
                if current_vol and current_vol > 0.7:
                    self._pipewire.set_volume(65)
                    self._overlay.update(OverlayPayload(
                        state=OverlayState.ALERT,
                        line1=f"🎧 {device_name} conectado",
                        line2="Volume ajustado para 65% (proteção auditiva).",
                        auto_hide_s=5.0,
                    ))
                else:
                    self._overlay.update(OverlayPayload(
                        state=OverlayState.IDLE,
                        line1=f"🎧 {device_name} conectado",
                        auto_hide_s=3.0,
                    ))
            else:
                self._overlay.update(OverlayPayload(
                    state=OverlayState.IDLE,
                    line1=f"🔌 {device_name} conectado [{device_type}]",
                    auto_hide_s=3.0,
                ))

        elif action == "remove":
            if device_type == "audio":
                self._overlay.update(OverlayPayload(
                    state=OverlayState.IDLE,
                    line1=f"🔌 {device_name} desconectado",
                    auto_hide_s=2.0,
                ))

    # ═══════════════════════════════════════════════════════════
    #  Volume Control Handler
    # ═══════════════════════════════════════════════════════════

    def _handle_volume(self, kwargs: Dict) -> TaskResult:
        action = kwargs.get("action", "get")
        device = kwargs.get("device", "@DEFAULT_AUDIO_SINK@")

        if action == "get":
            vol = self._pipewire.get_volume(device)
            return TaskResult(success=vol is not None, data={"volume": vol, "device": device})

        if action == "set":
            value = int(kwargs.get("value", 70))
            ok    = self._pipewire.set_volume(value, device)
            return TaskResult(success=ok, data={"volume": value, "device": device})

        if action == "up":
            step    = int(kwargs.get("step", 10))
            current = self._pipewire.get_volume(device) or 0.5
            new_vol = min(100, int(current * 100) + step)
            ok      = self._pipewire.set_volume(new_vol, device)
            return TaskResult(success=ok, data={"volume": new_vol})

        if action == "down":
            step    = int(kwargs.get("step", 10))
            current = self._pipewire.get_volume(device) or 0.5
            new_vol = max(0, int(current * 100) - step)
            ok      = self._pipewire.set_volume(new_vol, device)
            return TaskResult(success=ok, data={"volume": new_vol})

        return TaskResult(success=False, error=f"Unknown volume action: '{action}'")

    # ═══════════════════════════════════════════════════════════
    #  Status
    # ═══════════════════════════════════════════════════════════

    def _get_status(self) -> Dict[str, Any]:
        vol = self._pipewire.get_volume()
        return {
            "overlay_available":  self._overlay._gtk_available,
            "overlay_state":      OverlayState.RECORDING.value if self._is_recording else OverlayState.IDLE.value,
            "hotkey_backend":     self._hotkey._backend,
            "hotkey":             self._hotkey._hotkey,
            "dbus_available":     self._dbus._available,
            "udev_available":     self._udev._thread is not None,
            "current_volume":     f"{int((vol or 0.0) * 100)}%" if vol is not None else "unknown",
            "battery_percent":    self._last_battery_pct,
            "transcriber_model":  "whisper-large-v3-turbo",
            "mic_device":         self._audio._device,
            "audio_devices":      len(AudioCapture.list_devices()),
        }


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _int_env(key: str, default: Optional[int]) -> Optional[int]:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default
