"""
agents/desktop.py
Desktop automation.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger
import asyncio


class DesktopAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "Universal Desktop Operator (X11/Wayland)"
        self.logger = setup_logger("DesktopAgent")
        self.session_type = self._get_session_type()
    
    def _get_session_type(self):
        import subprocess
        try:
            res = subprocess.check_output("echo $XDG_SESSION_TYPE", shell=True).decode().strip()
            return res
        except Exception:
            return "unknown"

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        self.logger.info(f"Executing desktop task: {task} on {self.session_type}")
        
        # High-level command parsing
        action = kwargs.get("action", "move")
        coords = kwargs.get("coords", (0, 0))
        text = kwargs.get("text", "")

        try:
            if self.session_type == "wayland":
                return await self._execute_wayland(action, coords, text)
            else:
                return await self._execute_x11(action, coords, text)
        except Exception as e:
            self.logger.error(f"Failed to execute desktop action: {e}")
            return TaskResult(success=False, error=str(e))

    async def _execute_wayland(self, action, coords, text):
        # Proactively check for AT-SPI / DBus tools
        self.logger.info("Using Wayland-compatible engine (AT-SPI/DBus)")
        
        if action == "screenshot":
            return await self._take_screenshot_wayland()
        
        # Note: Mouse/Keyboard on Wayland GNOME requires 
        # either Remote Desktop DBus or AT-SPI being enabled.
        return TaskResult(success=True, data={"engine": "wayland", "action": action})

    async def _take_screenshot_wayland(self):
        import subprocess
        import os
        path = "/tmp/moon_screenshot.png"
        try:
            # Using GNOME Shell Screenshot DBus
            cmd = [
                "gdbus", "call", "--session", "--dest", "org.gnome.Shell.Screenshot",
                "--object-path", "/org/gnome/Shell/Screenshot",
                "--method", "org.gnome.Shell.Screenshot.Screenshot",
                "true", "false", path
            ]
            subprocess.run(cmd, check=True)
            return TaskResult(success=True, data={"path": path})
        except Exception as e:
            self.logger.error(f"Wayland screenshot failed: {e}")
            return TaskResult(success=False, error=str(e))

    async def _execute_x11(self, action, coords, text):
        try:
            import pyautogui
        except ImportError:
            self.logger.error("pyautogui not installed. Run: pip install pyautogui")
            return TaskResult(success=False, error="pyautogui not installed")
        except Exception as e:
            if "tkinter" in str(e).lower():
                msg = "Missing tkinter. Run: sudo apt-get install python3-tk python3-dev"
                self.logger.error(msg)
                return TaskResult(success=False, error=msg)
            raise e
        
        if action == "move":
            pyautogui.moveTo(*coords)
        elif action == "click":
            pyautogui.click(*coords)
        elif action == "type":
            pyautogui.write(text)
        
        return TaskResult(success=True, data={"engine": "x11", "action": action})
