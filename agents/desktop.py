"""
agents/desktop.py
Desktop automation with OCR and advanced interaction capabilities.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger
import asyncio
import os
import subprocess


class DesktopAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "Universal Desktop Operator (X11/Wayland) with OCR"
        self.logger = setup_logger("DesktopAgent")
        self.session_type = self._get_session_type()
        self.dependencies = {
            "tesseract": False,
            "pytesseract": False,
            "pyautogui": False,
            "pillow": False,
            "grim": False,
            "slurp": False,
            "xdotool": False,
            "wmctrl": False
        }
        self._check_dependencies()
    
    def _get_session_type(self):
        try:
            res = subprocess.check_output("echo $XDG_SESSION_TYPE", shell=True).decode().strip()
            return res.lower()
        except Exception:
            return "unknown"

    def _check_dependencies(self):
        """Check for required system and python tools."""
        try:
            import pytesseract
            self.dependencies["pytesseract"] = True
        except ImportError: pass
        
        try:
            import pyautogui
            self.dependencies["pyautogui"] = True
        except ImportError: pass

        try:
            from PIL import Image
            self.dependencies["pillow"] = True
        except ImportError: pass

        # System tools
        tools = ["tesseract", "grim", "slurp", "xdotool", "wmctrl"]
        for tool in tools:
            self.dependencies[tool] = subprocess.call(f"which {tool}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        self.logger.info(f"Executing desktop task: {task} on {self.session_type}")
        
        action = kwargs.get("action", "health_check")
        
        if action == "health_check":
            self._check_dependencies()
            return TaskResult(success=True, data=self.dependencies)

        try:
            if action == "ocr":
                return await self.perform_ocr(kwargs.get("region"))
            
            if self.session_type == "wayland":
                return await self._execute_wayland(action, **kwargs)
            else:
                return await self._execute_x11(action, **kwargs)
        except Exception as e:
            self.logger.error(f"Failed to execute desktop action: {e}")
            return TaskResult(success=False, error=str(e))

    async def perform_ocr(self, region=None) -> TaskResult:
        """Perform OCR on a screen region or the whole screen."""
        if not self.dependencies["pytesseract"] or not self.dependencies["tesseract"]:
            return TaskResult(success=False, error="Tesseract or pytesseract not installed.")
        
        import pytesseract
        from PIL import Image
        
        screenshot_res = await self._take_screenshot()
        if not screenshot_res.success:
            return screenshot_res
        
        img_path = screenshot_res.data["path"]
        try:
            img = Image.open(img_path)
            if region: # region is (x, y, w, h)
                img = img.crop((region[0], region[1], region[0] + region[2], region[1] + region[3]))
            
            text = pytesseract.image_to_string(img)
            return TaskResult(success=True, data={"text": text, "path": img_path})
        except Exception as e:
            return TaskResult(success=False, error=f"OCR failed: {e}")

    async def _take_screenshot(self) -> TaskResult:
        if self.session_type == "wayland":
            return await self._take_screenshot_wayland()
        else:
            return await self._take_screenshot_x11()

    async def _take_screenshot_wayland(self):
        path = "/tmp/moon_screenshot.png"
        # Try grim first if available
        if self.dependencies["grim"]:
            try:
                subprocess.run(["grim", path], check=True)
                return TaskResult(success=True, data={"path": path})
            except Exception: pass
            
        # Fallback to GNOME DBus (as in original)
        try:
            cmd = [
                "gdbus", "call", "--session", "--dest", "org.gnome.Shell.Screenshot",
                "--object-path", "/org/gnome/Shell/Screenshot",
                "--method", "org.gnome.Shell.Screenshot.Screenshot",
                "true", "false", path
            ]
            subprocess.run(cmd, check=True)
            return TaskResult(success=True, data={"path": path})
        except Exception as e:
            return TaskResult(success=False, error=f"Wayland screenshot failed: {e}")

    async def _take_screenshot_x11(self):
        path = "/tmp/moon_screenshot.png"
        if not self.dependencies["pyautogui"]:
            return TaskResult(success=False, error="pyautogui not installed")
        
        import pyautogui
        try:
            pyautogui.screenshot(path)
            return TaskResult(success=True, data={"path": path})
        except Exception as e:
            return TaskResult(success=False, error=f"X11 screenshot failed: {e}")

    async def _execute_wayland(self, action, **kwargs):
        coords = kwargs.get("coords", (0, 0))
        text = kwargs.get("text", "")
        
        if action == "screenshot":
            return await self._take_screenshot_wayland()
        
        # Add basic window management if tools available
        if action == "list_windows" and self.dependencies["wmctrl"]:
            res = subprocess.check_output("wmctrl -l", shell=True).decode()
            return TaskResult(success=True, data={"windows": res})

        return TaskResult(success=False, error=f"Action {action} not fully implemented for Wayland yet.")

    async def _execute_x11(self, action, **kwargs):
        coords = kwargs.get("coords", (0, 0))
        text = kwargs.get("text", "")

        if not self.dependencies["pyautogui"]:
            return TaskResult(success=False, error="pyautogui not installed")
        
        import pyautogui
        if action == "move":
            pyautogui.moveTo(*coords)
        elif action == "click":
            pyautogui.click(*coords)
        elif action == "type":
            pyautogui.write(text)
        elif action == "screenshot":
            return await self._take_screenshot_x11()
        
        return TaskResult(success=True, data={"engine": "x11", "action": action})
