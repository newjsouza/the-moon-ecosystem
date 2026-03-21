"""
agents/qwen_code_agent.py
Headless Qwen Code agent.
Wraps `qwen -p <task> --output-format json` via subprocess.
Used for: code generation, refactoring, test writing, harness generation.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional

from core.agent_base import AgentBase, TaskResult


class QwenCodeAgent(AgentBase):
    """
    Headless Qwen Code agent.
    Wraps `qwen -p <task> --output-format json` via subprocess.
    Used for: code generation, refactoring, test writing, harness generation.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "QwenCodeAgent"
        self.description = "Headless Qwen Code CLI wrapper for code generation and refactoring"
        self._qwen_bin = "qwen"

    async def _execute(self, task: str, **kwargs: Any) -> TaskResult:
        """
        Executes qwen CLI in headless mode.

        Args:
            task: The prompt/task to send to qwen
            kwargs:
                cwd: Working directory (default: current dir)
                flags: Extra CLI flags (default: [])
                timeout: Timeout in seconds (default: 120)

        Returns:
            TaskResult with JSON response from qwen
        """
        start = time.time()
        cwd = kwargs.get("cwd", os.getcwd())
        extra_flags = kwargs.get("flags", [])
        timeout = kwargs.get("timeout", 120)

        cmd = [
            self._qwen_bin,
            "-p", task,
            "--output-format", "json",
            *extra_flags
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ}
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                return TaskResult(
                    success=False,
                    error=f"QwenCodeAgent timeout after {timeout}s",
                    execution_time=time.time() - start
                )

            elapsed = time.time() - start

            if proc.returncode != 0:
                return TaskResult(
                    success=False,
                    error=stderr.decode().strip(),
                    execution_time=elapsed
                )

            # Parse JSON response
            try:
                data = json.loads(stdout.decode())
            except json.JSONDecodeError:
                # Fallback: return raw output
                data = {"response": stdout.decode().strip()}

            return TaskResult(
                success=True,
                data=data,
                execution_time=elapsed
            )

        except FileNotFoundError:
            return TaskResult(
                success=False,
                error="qwen binary not found — run: npm install -g @qwen-code/qwen-code",
                execution_time=time.time() - start
            )
        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )

    async def ping(self) -> bool:
        """Lightweight liveness probe for the Orchestrator health check."""
        # Check if qwen binary is available
        try:
            proc = await asyncio.create_subprocess_exec(
                self._qwen_bin, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Returns agent status information."""
        return {
            "name": self.name,
            "qwen_bin": self._qwen_bin,
            "description": self.description,
        }
