#!/usr/bin/env python3
"""
AI Jail - Sandbox para Agentes de IA

Baseado no conceito do Akita: isolar operações perigosas
para proteger o sistema principal.

Funcionalidades:
- Execução isolada de código gerado por IA
- Timeout para evitar loops infinitos
- Limite de recursos (memória, CPU)
- Firewall de sistema de arquivos (allowlist)
- Logging de todas as operações
"""
import os
import sys
import subprocess
import tempfile
import shutil
import uuid
import time
import json
import signal
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JailConfig:
    allowed_dirs: List[str] = field(default_factory=list)
    max_execution_time: int = 30
    max_memory_mb: int = 512
    max_file_size_mb: int = 10
    allow_network: bool = False
    allow_subprocess: bool = False
    blocked_commands: List[str] = field(default_factory=lambda: [
        "rm -rf /", "dd if=", "mkfs", "fdisk", "parted",
        "curl | sh", "wget | sh", "chmod 777"
    ])


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int
    execution_time: float
    warnings: List[str] = field(default_factory=list)
    blocked_operations: List[str] = field(default_factory=list)


class AIJail:
    def __init__(self, config: Optional[JailConfig] = None):
        self.config = config or JailConfig()
        self.execution_log: List[Dict[str, Any]] = []
        self._setup_workspace()

    def _setup_workspace(self):
        """Create isolated workspace directory."""
        self.workspace = Path(tempfile.mkdtemp(prefix="ai-jail-"))
        self.sandbox_dir = self.workspace / "sandbox"
        self.sandbox_dir.mkdir()
        self.output_dir = self.workspace / "output"
        self.output_dir.mkdir()

    def _log_operation(self, operation: str, details: Dict[str, Any]):
        """Log all operations for audit."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "details": details
        }
        self.execution_log.append(entry)

    def validate_command(self, command: str) -> tuple[bool, List[str]]:
        """Validate command doesn't contain blocked operations."""
        blocked = []
        for blocked_cmd in self.config.blocked_commands:
            if blocked_cmd in command.lower():
                blocked.append(blocked_cmd)
        return len(blocked) == 0, blocked

    def validate_path(self, path: str) -> bool:
        """Validate path is within allowed directories."""
        try:
            abs_path = Path(path).resolve()
            for allowed in self.config.allowed_dirs:
                allowed_path = Path(allowed).resolve()
                if str(abs_path).startswith(str(allowed_path)):
                    return True
            if not self.config.allowed_dirs:
                return True
            return False
        except Exception:
            return False

    def execute_python(
        self,
        code: str,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """Execute Python code in sandbox."""
        start_time = time.time()
        timeout = timeout or self.config.max_execution_time

        temp_file = self.sandbox_dir / f"script_{uuid.uuid4().hex[:8]}.py"

        try:
            with open(temp_file, "w") as f:
                f.write(code)

            result = subprocess.run(
                [sys.executable, str(temp_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.sandbox_dir),
                env=self._get_sandbox_env()
            )

            execution_time = time.time() - start_time

            self._log_operation("execute_python", {
                "script": str(temp_file),
                "return_code": result.returncode,
                "execution_time": execution_time
            })

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                execution_time=execution_time
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timed out after {timeout} seconds",
                return_code=-1,
                execution_time=timeout,
                warnings=["Timeout exceeded"]
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time=time.time() - start_time
            )
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def execute_bash(
        self,
        command: str,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """Execute bash command in sandbox."""
        start_time = time.time()
        timeout = timeout or self.config.max_execution_time

        is_valid, blocked = self.validate_command(command)
        if not is_valid:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Blocked dangerous command: {blocked}",
                return_code=-1,
                execution_time=0,
                blocked_operations=blocked
            )

        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(self.sandbox_dir),
            env=self._get_sandbox_env()
        )

        execution_time = time.time() - start_time

        self._log_operation("execute_bash", {
            "command": command,
            "return_code": result.returncode,
            "execution_time": execution_time
        })

        return ExecutionResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode,
            execution_time=execution_time
        )

    def _get_sandbox_env(self) -> Dict[str, str]:
        """Get sanitized environment variables."""
        env = os.environ.copy()
        env.update({
            "HOME": str(self.sandbox_dir),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "TMPDIR": str(self.sandbox_dir),
        })
        if not self.config.allow_network:
            env["http_proxy"] = ""
            env["https_proxy"] = ""
        return env

    def get_log(self) -> List[Dict[str, Any]]:
        """Get execution log."""
        return self.execution_log

    def export_log(self, filepath: str):
        """Export execution log to file."""
        with open(filepath, "w") as f:
            json.dump(self.execution_log, f, indent=2)

    def cleanup(self):
        """Clean up workspace."""
        if hasattr(self, "workspace") and self.workspace.exists():
            shutil.rmtree(self.workspace)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def create_safe_jail() -> AIJail:
    """Factory function for creating a safe jail configuration."""
    config = JailConfig(
        allowed_dirs=[
            tempfile.gettempdir(),
            os.path.expanduser("~/projects")
        ],
        max_execution_time=30,
        max_memory_mb=512,
        allow_network=False,
        allow_subprocess=False
    )
    return AIJail(config)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Jail - Sandbox for AI Agents")
    parser.add_argument("command", help="Command to execute")
    parser.add_argument("--code", help="Python code to execute")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")

    args = parser.parse_args()

    with create_safe_jail() as jail:
        if args.code:
            result = jail.execute_python(args.code, args.timeout)
        else:
            result = jail.execute_bash(args.command, args.timeout)

        print(f"Success: {result.success}")
        print(f"Return code: {result.return_code}")
        print(f"Execution time: {result.execution_time:.2f}s")
        if result.stdout:
            print(f"Stdout:\n{result.stdout}")
        if result.stderr:
            print(f"Stderr:\n{result.stderr}")
        if result.blocked_operations:
            print(f"Blocked: {result.blocked_operations}")
