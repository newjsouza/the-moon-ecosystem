"""OBS Studio integration via CLI harness for recording and streaming."""
import asyncio
import shutil
from pathlib import Path
from core.agent_base import TaskResult


class MoonOBSRecorder:
    """Control OBS Studio for screen recording via CLI."""

    OBS_CMD = "obs"

    def _obs_available(self) -> bool:
        return shutil.which(self.OBS_CMD) is not None

    async def check_installation(self, **kwargs) -> TaskResult:
        """Verifica se OBS Studio está instalado e acessível."""
        start = asyncio.get_event_loop().time()
        if not self._obs_available():
            return TaskResult(success=False,
                              error="OBS Studio não encontrado no PATH. Instale: sudo apt install obs-studio")
        try:
            proc = await asyncio.create_subprocess_exec(
                self.OBS_CMD, "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            version_output = stdout.decode().strip() or stderr.decode().strip()
            return TaskResult(
                success=True,
                data={"version": version_output, "available": True},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def start_recording(self, output_path: str,
                               scene: str = None, **kwargs) -> TaskResult:
        """Inicia gravação via OBS CLI (requer websocket plugin configurado)."""
        start = asyncio.get_event_loop().time()
        if not self._obs_available():
            return TaskResult(success=False, error="OBS Studio não instalado")
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)

            cmd = [self.OBS_CMD, "--startrecording", "--minimize-to-tray"]
            if scene:
                cmd += ["--scene", scene]

            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await asyncio.sleep(2)

            return TaskResult(
                success=True,
                data={"status": "recording_started", "output_path": str(out), "pid": proc.pid},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def stop_recording(self, **kwargs) -> TaskResult:
        """Para a gravação OBS em andamento."""
        start = asyncio.get_event_loop().time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "pkill", "-f", "obs",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return TaskResult(
                success=True,
                data={"status": "recording_stopped"},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))