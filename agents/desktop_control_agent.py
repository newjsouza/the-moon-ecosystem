"""
agents/desktop_control_agent.py
DesktopControlAgent — Abelha Operária da Colmeia.
Controle completo do desktop Linux/X11 via pyautogui + xdotool + pytesseract.
"""
import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.agent_base import AgentBase, TaskResult
from core.message_bus import MessageBus
from agents.llm import LLMRouter

logger = logging.getLogger(__name__)

_SCREENSHOTS_DIR = Path("data/screenshots")
_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_MIN_ACTION_INTERVAL = 0.3


def _require_display() -> bool:
    """Retorna True se DISPLAY estiver disponível (X11)."""
    return bool(os.environ.get("DISPLAY"))


class DesktopControlAgent(AgentBase):
    """
    Abelha Operária da Colmeia.
    Controle completo do desktop Linux/X11.
    """

    def __init__(self, bus: MessageBus, llm: LLMRouter):
        super().__init__()
        self.name = "DesktopControlAgent"
        self.description = "Controle do desktop via pyautogui + xdotool + OCR"
        self._bus = bus
        self._llm = llm
        self._display_available = _require_display()
        self._last_action_time: float = 0.0
        self._pyautogui = None
        self._mss = None
        self._pytesseract = None
        self._xdotool_available = False

    async def start(self) -> None:
        await self._lazy_import()
        self._bus.subscribe("desktop.action", self._on_desktop_action_wrapper)
        asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "DesktopControlAgent iniciado — display: %s",
            os.environ.get("DISPLAY", "não disponível"),
        )

    async def _lazy_import(self) -> None:
        """Imports lazy para não quebrar em ambientes headless."""
        if not self._display_available:
            logger.warning("DesktopControlAgent: DISPLAY não encontrado — modo limitado")
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._do_imports)
        except Exception as exc:
            self._display_available = False
            logger.warning(
                "DesktopControlAgent: display indisponível (%s) — modo limitado",
                exc,
            )
            return
        # Verificar xdotool
        try:
            result = subprocess.run(["xdotool", "--version"], capture_output=True, timeout=2)
            self._xdotool_available = (result.returncode == 0)
        except Exception:
            self._xdotool_available = False

    def _do_imports(self) -> None:
        import pyautogui
        import mss as mss_module
        import pytesseract as tess
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = _MIN_ACTION_INTERVAL
        self._pyautogui = pyautogui
        self._mss = mss_module
        self._pytesseract = tess

    def _check_display(self) -> None:
        if not self._display_available or self._pyautogui is None:
            raise RuntimeError(
                "DesktopControlAgent requer DISPLAY X11 e pyautogui carregado."
            )

    async def _throttle(self) -> None:
        elapsed = time.time() - self._last_action_time
        if elapsed < _MIN_ACTION_INTERVAL:
            await asyncio.sleep(_MIN_ACTION_INTERVAL - elapsed)
        self._last_action_time = time.time()

    # ─────────────────────────────────────────────
    # MOUSE
    # ─────────────────────────────────────────────

    async def click(self, x: int, y: int, button: str = "left") -> None:
        self._check_display()
        await self._throttle()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.click(x, y, button=button)
        )

    async def double_click(self, x: int, y: int) -> None:
        self._check_display()
        await self._throttle()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.doubleClick(x, y)
        )

    async def right_click(self, x: int, y: int) -> None:
        await self.click(x, y, button="right")

    async def move_to(self, x: int, y: int, duration: float = 0.2) -> None:
        self._check_display()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.moveTo(x, y, duration=duration)
        )

    async def drag_to(
        self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5
    ) -> None:
        self._check_display()
        await self._throttle()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._pyautogui.drag(x1, y1, x2, y2, duration=duration),
        )

    async def scroll(self, x: int, y: int, clicks: int = 3) -> None:
        self._check_display()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.scroll(clicks, x=x, y=y)
        )

    async def get_mouse_position(self) -> dict:
        self._check_display()
        loop = asyncio.get_event_loop()
        pos = await loop.run_in_executor(None, self._pyautogui.position)
        return {"x": pos.x, "y": pos.y}

    # ─────────────────────────────────────────────
    # TECLADO
    # ─────────────────────────────────────────────

    async def type_text(self, text: str, interval: float = 0.05) -> None:
        self._check_display()
        await self._throttle()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.typewrite(text, interval=interval)
        )

    async def press_key(self, key: str) -> None:
        self._check_display()
        await self._throttle()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.press(key)
        )

    async def hotkey(self, *keys: str) -> None:
        self._check_display()
        await self._throttle()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.hotkey(*keys)
        )

    async def key_down(self, key: str) -> None:
        self._check_display()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.keyDown(key)
        )

    async def key_up(self, key: str) -> None:
        self._check_display()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self._pyautogui.keyUp(key)
        )

    # ─────────────────────────────────────────────
    # TELA / OCR
    # ─────────────────────────────────────────────

    async def screenshot(
        self,
        region: dict | None = None,
        save: bool = True,
        filename: str | None = None,
    ) -> dict:
        self._check_display()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self._take_screenshot(region, save, filename)
        )
        return result

    def _take_screenshot(
        self, region: dict | None, save: bool, filename: str | None
    ) -> dict:
        with self._mss.mss() as sct:
            monitor = (
                {
                    "top": region["top"],
                    "left": region["left"],
                    "width": region["width"],
                    "height": region["height"],
                }
                if region
                else sct.monitors[1]
            )
            img = sct.grab(monitor)
        path = None
        if save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            fname = filename or f"screenshot_{ts}.png"
            path = str(_SCREENSHOTS_DIR / fname)
            self._mss.tools.to_png(img.rgb, img.size, output=path)
        return {
            "width": img.width,
            "height": img.height,
            "path": path,
            "region": region,
        }

    async def ocr_screen(
        self,
        region: dict | None = None,
        lang: str = "por+eng",
    ) -> str:
        self._check_display()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._ocr(region, lang)
        )

    def _ocr(self, region: dict | None, lang: str) -> str:
        from PIL import Image
        with self._mss.mss() as sct:
            monitor = (
                {
                    "top": region["top"], "left": region["left"],
                    "width": region["width"], "height": region["height"],
                }
                if region
                else sct.monitors[1]
            )
            img_data = sct.grab(monitor)
            pil_img = Image.frombytes("RGB", img_data.size, img_data.rgb)
        text = self._pytesseract.image_to_string(pil_img, lang=lang)
        return text.strip()

    async def find_on_screen(self, image_path: str, confidence: float = 0.8) -> dict | None:
        self._check_display()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._locate_image(image_path, confidence)
        )

    def _locate_image(self, image_path: str, confidence: float) -> dict | None:
        location = self._pyautogui.locateOnScreen(image_path, confidence=confidence)
        if location is None:
            return None
        return {
            "left": location.left, "top": location.top,
            "width": location.width, "height": location.height,
            "center_x": location.left + location.width // 2,
            "center_y": location.top + location.height // 2,
        }

    async def get_screen_size(self) -> dict:
        self._check_display()
        loop = asyncio.get_event_loop()
        size = await loop.run_in_executor(None, self._pyautogui.size)
        return {"width": size.width, "height": size.height}

    # ─────────────────────────────────────────────
    # JANELAS (xdotool)
    # ─────────────────────────────────────────────

    def _xdotool(self, *args: str) -> str:
        if not self._xdotool_available:
            raise RuntimeError("xdotool não disponível no sistema")
        result = subprocess.run(
            ["xdotool"] + list(args),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(f"xdotool erro: {result.stderr.strip()}")
        return result.stdout.strip()

    async def _run_xdotool(self, *args: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._xdotool(*args))

    async def list_windows(self) -> list[dict]:
        output = await self._run_xdotool("search", "--onlyvisible", "--name", "")
        if not output:
            return []
        window_ids = output.strip().splitlines()
        windows = []
        for wid in window_ids[:30]:
            try:
                name = await self._run_xdotool("getwindowname", wid)
                windows.append({"id": wid, "name": name})
            except Exception:
                continue
        return windows

    async def find_window(self, name: str) -> list[dict]:
        try:
            output = await self._run_xdotool("search", "--name", name)
            ids = output.strip().splitlines()
            results = []
            for wid in ids:
                try:
                    wname = await self._run_xdotool("getwindowname", wid)
                    results.append({"id": wid, "name": wname})
                except Exception:
                    continue
            return results
        except RuntimeError:
            return []

    async def focus_window(self, window_id: str) -> None:
        await self._run_xdotool("windowfocus", "--sync", window_id)
        await self._run_xdotool("windowraise", window_id)

    async def resize_window(self, window_id: str, width: int, height: int) -> None:
        await self._run_xdotool("windowsize", window_id, str(width), str(height))

    async def move_window(self, window_id: str, x: int, y: int) -> None:
        await self._run_xdotool("windowmove", window_id, str(x), str(y))

    async def close_window(self, window_id: str) -> None:
        await self._run_xdotool("windowclose", window_id)

    async def get_active_window(self) -> dict:
        wid = await self._run_xdotool("getactivewindow")
        name = await self._run_xdotool("getwindowname", wid)
        return {"id": wid, "name": name}

    # ─────────────────────────────────────────────
    # MACRO
    # ─────────────────────────────────────────────

    async def run_macro(self, steps: list[dict]) -> list[dict]:
        results = []
        for i, step in enumerate(steps):
            action = step.get("action", "")
            params = step.get("params", {})
            step_result = {"step": i, "action": action, "success": False, "error": None}
            try:
                result = await self._execute(action, **params)
                step_result["success"] = result.success
                step_result["data"] = result.data
                if not result.success:
                    step_result["error"] = result.error
                    if step.get("abort_on_error", False):
                        results.append(step_result)
                        break
            except Exception as e:
                step_result["error"] = str(e)
            results.append(step_result)
            if step.get("delay_after"):
                await asyncio.sleep(step["delay_after"])
        return results

    # ─────────────────────────────────────────────
    # MESSAGEBUS HANDLERS
    # ─────────────────────────────────────────────

    def _on_desktop_action_wrapper(self, message: Any) -> None:
        sender = getattr(message, "sender", "unknown")
        payload = getattr(message, "payload", {})
        asyncio.create_task(self._on_desktop_action(sender, payload))

    async def _on_desktop_action(self, sender: str, payload: dict) -> None:
        action = payload.get("action", "")
        params = payload.get("params", {})
        request_id = payload.get("request_id")
        logger.info("desktop.action recebido: action=%s de=%s", action, sender)
        result = await self._execute(action, **params)
        await self._bus.publish(
            "DesktopControlAgent",
            "desktop.result",
            {
                "request_id": request_id,
                "action": action,
                "success": result.success,
                "data": result.data,
                "error": result.error,
            },
            target=sender,
        )

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            await self._bus.publish(
                "DesktopControlAgent",
                "hive.heartbeat",
                {
                    "status": "alive",
                    "display_available": self._display_available,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

    # ─────────────────────────────────────────────
    # _execute
    # ─────────────────────────────────────────────

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        start = time.time()
        try:
            # ── Mouse ──────────────────────────
            if task == "click":
                await self.click(kwargs["x"], kwargs["y"], kwargs.get("button", "left"))
                return TaskResult(success=True, data={"x": kwargs["x"], "y": kwargs["y"]},
                                  execution_time=time.time() - start)

            if task == "double_click":
                await self.double_click(kwargs["x"], kwargs["y"])
                return TaskResult(success=True, data={}, execution_time=time.time() - start)

            if task == "right_click":
                await self.right_click(kwargs["x"], kwargs["y"])
                return TaskResult(success=True, data={}, execution_time=time.time() - start)

            if task == "move_to":
                await self.move_to(kwargs["x"], kwargs["y"], kwargs.get("duration", 0.2))
                return TaskResult(success=True, data={}, execution_time=time.time() - start)

            if task == "drag_to":
                await self.drag_to(kwargs["x1"], kwargs["y1"], kwargs["x2"], kwargs["y2"],
                                   kwargs.get("duration", 0.5))
                return TaskResult(success=True, data={}, execution_time=time.time() - start)

            if task == "scroll":
                await self.scroll(kwargs["x"], kwargs["y"], kwargs.get("clicks", 3))
                return TaskResult(success=True, data={}, execution_time=time.time() - start)

            if task == "get_mouse_position":
                pos = await self.get_mouse_position()
                return TaskResult(success=True, data=pos, execution_time=time.time() - start)

            # ── Teclado ────────────────────────
            if task == "type_text":
                await self.type_text(kwargs["text"], kwargs.get("interval", 0.05))
                return TaskResult(success=True, data={"chars": len(kwargs["text"])},
                                  execution_time=time.time() - start)

            if task == "press_key":
                await self.press_key(kwargs["key"])
                return TaskResult(success=True, data={"key": kwargs["key"]},
                                  execution_time=time.time() - start)

            if task == "hotkey":
                await self.hotkey(*kwargs["keys"])
                return TaskResult(success=True, data={"keys": kwargs["keys"]},
                                  execution_time=time.time() - start)

            # ── Tela / OCR ─────────────────────
            if task == "screenshot":
                data = await self.screenshot(region=kwargs.get("region"), save=kwargs.get("save", True),
                                             filename=kwargs.get("filename"))
                return TaskResult(success=True, data=data, execution_time=time.time() - start)

            if task == "ocr_screen":
                text = await self.ocr_screen(region=kwargs.get("region"), lang=kwargs.get("lang", "por+eng"))
                return TaskResult(success=True, data={"text": text, "chars": len(text)},
                                  execution_time=time.time() - start)

            if task == "find_on_screen":
                location = await self.find_on_screen(kwargs["image_path"], kwargs.get("confidence", 0.8))
                return TaskResult(success=location is not None,
                                  data=location or {"found": False},
                                  execution_time=time.time() - start)

            if task == "get_screen_size":
                size = await self.get_screen_size()
                return TaskResult(success=True, data=size, execution_time=time.time() - start)

            # ── Janelas ────────────────────────
            if task == "list_windows":
                windows = await self.list_windows()
                return TaskResult(success=True, data={"windows": windows, "count": len(windows)},
                                  execution_time=time.time() - start)

            if task == "find_window":
                windows = await self.find_window(kwargs["name"])
                return TaskResult(success=True, data={"windows": windows, "count": len(windows)},
                                  execution_time=time.time() - start)

            if task == "focus_window":
                await self.focus_window(kwargs["window_id"])
                return TaskResult(success=True, data={"window_id": kwargs["window_id"]},
                                  execution_time=time.time() - start)

            if task == "resize_window":
                await self.resize_window(kwargs["window_id"], kwargs["width"], kwargs["height"])
                return TaskResult(success=True, data={}, execution_time=time.time() - start)

            if task == "move_window":
                await self.move_window(kwargs["window_id"], kwargs["x"], kwargs["y"])
                return TaskResult(success=True, data={}, execution_time=time.time() - start)

            if task == "close_window":
                await self.close_window(kwargs["window_id"])
                return TaskResult(success=True, data={"window_id": kwargs["window_id"]},
                                  execution_time=time.time() - start)

            if task == "get_active_window":
                window = await self.get_active_window()
                return TaskResult(success=True, data=window, execution_time=time.time() - start)

            # ── Macro ──────────────────────────
            if task == "run_macro":
                steps = kwargs.get("steps", [])
                if not steps:
                    return TaskResult(success=False, error="Parâmetro 'steps' obrigatório e não pode ser vazio",
                                      execution_time=time.time() - start)
                results = await self.run_macro(steps)
                success = all(r["success"] for r in results)
                return TaskResult(success=success,
                                  data={"steps": results, "total": len(results),
                                        "ok": sum(1 for r in results if r["success"])},
                                  execution_time=time.time() - start)

            if task == "status":
                return TaskResult(
                    success=True,
                    data={
                        "display_available": self._display_available,
                        "display": os.environ.get("DISPLAY", ""),
                        "pyautogui_loaded": self._pyautogui is not None,
                        "xdotool_available": self._xdotool_available,
                        "screenshots_dir": str(_SCREENSHOTS_DIR),
                    },
                    execution_time=time.time() - start,
                )

            return TaskResult(success=False, error=f"Task desconhecida: {task}",
                              execution_time=time.time() - start)

        except KeyError as e:
            return TaskResult(success=False, error=f"Parâmetro obrigatório ausente: {e}",
                              execution_time=time.time() - start)
        except RuntimeError as e:
            return TaskResult(success=False, error=str(e),
                              execution_time=time.time() - start)
        except Exception as e:
            logger.exception("DesktopControlAgent._execute falhou: task=%s", task)
            return TaskResult(success=False, error=str(e),
                              execution_time=time.time() - start)
