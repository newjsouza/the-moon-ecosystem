"""
core/cli_harness_adapter.py

CLIHarnessAdapter — Bridge assíncrona para CLI-Anything harnesses instalados.
Permite que qualquer agente The Moon execute harnesses via subprocess seguro.

Parte do Moon-Stack CLI-Anything Integration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Padrão de logging do projeto (mesmo padrão de core/orchestrator.py)
logger = logging.getLogger("moon.core.cli_harness_adapter")

# Paths resolvidos a partir da raiz do projeto
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent  # core/../ = project root

HARNESS_REGISTRY_PATH = _PROJECT_ROOT / "skills" / "cli_harnesses" / "installed_harnesses.json"
RESULTS_PATH = _PROJECT_ROOT / "data" / "cli_harness_results"


class HarnessResult:
    """
    Resultado padronizado de execução de harness CLI-Anything.
    Contém output real, exit code, duração e metadados.
    Nunca lança exceção — erros são encapsulados no objeto.
    """

    def __init__(
        self,
        *,
        success: bool,
        output: Any,
        raw_stdout: str,
        raw_stderr: str,
        exit_code: int,
        command: list,
        harness: str,
        duration_ms: float,
    ):
        self.success = success
        self.output = output          # JSON parseado se possível, str caso contrário
        self.raw_stdout = raw_stdout
        self.raw_stderr = raw_stderr
        self.exit_code = exit_code
        self.command = command        # lista real de argv
        self.harness = harness
        self.duration_ms = round(duration_ms, 2)
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "exit_code": self.exit_code,
            "command": self.command,
            "harness": self.harness,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "stderr_preview": self.raw_stderr[:500] if self.raw_stderr else None,
        }

    def __repr__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"HarnessResult({status} harness={self.harness!r} "
            f"exit={self.exit_code} duration={self.duration_ms}ms)"
        )


class CLIHarnessAdapter:
    """
    Adapter assíncrono para CLI-Anything harnesses instalados.

    Uso básico:
        adapter = CLIHarnessAdapter()

        # Executar comando
        result = await adapter.run(
            "libreoffice",
            ["document", "new", "--type", "writer", "-o", "/tmp/doc.json"]
        )

        # Executar com --json flag automático
        result = await adapter.run_json(
            "mermaid",
            ["diagram", "render", "--input", "arch.mmd", "--output", "arch.png"]
        )

        # Verificar disponibilidade
        if adapter.is_available("libreoffice"):
            ...

        # Listar tudo disponível
        available = adapter.list_available()
    """

    def __init__(self):
        self._registry: dict[str, dict] = {}
        self._load_registry()
        RESULTS_PATH.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> None:
        """
        Carrega registry REAL de harnesses instalados.
        Silencioso se registry não existir — retorna registry vazio.
        """
        if not HARNESS_REGISTRY_PATH.exists():
            logger.warning(
                f"CLIHarnessAdapter: registry não encontrado em {HARNESS_REGISTRY_PATH}. "
                "Execute a Fase 1 da integração CLI-Anything."
            )
            return

        try:
            data = json.loads(HARNESS_REGISTRY_PATH.read_text(encoding="utf-8"))
            for h in data.get("harnesses", []):
                if h.get("installed") and not h.get("skipped"):
                    self._registry[h["name"]] = h
            logger.info(
                f"CLIHarnessAdapter: {len(self._registry)} harnesses carregados "
                f"({', '.join(self._registry.keys()) or 'nenhum'})"
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"CLIHarnessAdapter: erro ao carregar registry: {exc}")

    def is_available(self, harness_name: str) -> bool:
        """
        Verifica se harness está registrado E binário real acessível no PATH.
        Dupla verificação: registry + shutil.which() em tempo real.
        """
        if harness_name not in self._registry:
            return False
        binary = self._registry[harness_name].get("binary")
        return bool(binary and shutil.which(binary))

    def list_available(self) -> list[dict]:
        """
        Lista harnesses disponíveis com metadados reais do registry.
        Filtra apenas os que têm binário acessível agora.
        """
        return [
            {
                "name": name,
                "binary": meta.get("binary"),
                "version": meta.get("version"),
                "path": meta.get("path"),
            }
            for name, meta in self._registry.items()
            if self.is_available(name)
        ]

    async def run(
        self,
        harness_name: str,
        args: list[str | int | Path],
        *,
        timeout: int = 90,
        workdir: Optional[str | Path] = None,
    ) -> HarnessResult:
        """
        Executa harness de forma assíncrona via subprocess real.
        Nunca lança exceção — erros são retornados em HarnessResult.

        Args:
            harness_name: nome do harness (ex: "libreoffice", "mermaid")
            args: argumentos adicionais ao binário
            timeout: timeout em segundos (default: 90)
            workdir: diretório de trabalho para o subprocess
        """
        if not self.is_available(harness_name):
            return HarnessResult(
                success=False,
                output=None,
                raw_stdout="",
                raw_stderr=(
                    f"Harness '{harness_name}' não disponível. "
                    f"Disponíveis: {[h['name'] for h in self.list_available()]}"
                ),
                exit_code=-1,
                command=[harness_name] + [str(a) for a in args],
                harness=harness_name,
                duration_ms=0.0,
            )

        binary = self._registry[harness_name]["binary"]
        cmd = [binary] + [str(a) for a in args]
        workdir_str = str(workdir) if workdir else None

        t_start = asyncio.get_event_loop().time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir_str,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return HarnessResult(
                    success=False,
                    output=None,
                    raw_stdout="",
                    raw_stderr=f"Timeout após {timeout}s — processo encerrado",
                    exit_code=-2,
                    command=cmd,
                    harness=harness_name,
                    duration_ms=(asyncio.get_event_loop().time() - t_start) * 1000,
                )

            duration_ms = (asyncio.get_event_loop().time() - t_start) * 1000
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
            success = proc.returncode == 0

            # Tentar parsear JSON do stdout
            parsed_output: Any = None
            try:
                parsed_output = json.loads(stdout_str)
            except (json.JSONDecodeError, ValueError):
                parsed_output = stdout_str.strip() or None

            result = HarnessResult(
                success=success,
                output=parsed_output,
                raw_stdout=stdout_str,
                raw_stderr=stderr_str,
                exit_code=proc.returncode,
                command=cmd,
                harness=harness_name,
                duration_ms=duration_ms,
            )

            logger.debug(
                f"CLIHarnessAdapter.run: {binary} → "
                f"exit={proc.returncode} duration={duration_ms:.0f}ms"
            )

            await self._persist_result(result)
            return result

        except FileNotFoundError:
            return HarnessResult(
                success=False,
                output=None,
                raw_stdout="",
                raw_stderr=f"Binário '{binary}' não encontrado (FileNotFoundError)",
                exit_code=-3,
                command=cmd,
                harness=harness_name,
                duration_ms=0.0,
            )
        except Exception as exc:
            logger.error(f"CLIHarnessAdapter.run: erro inesperado [{harness_name}]: {exc}")
            return HarnessResult(
                success=False,
                output=None,
                raw_stdout="",
                raw_stderr=str(exc),
                exit_code=-4,
                command=cmd,
                harness=harness_name,
                duration_ms=(asyncio.get_event_loop().time() - t_start) * 1000,
            )

    async def run_json(
        self,
        harness_name: str,
        args: list[str | int | Path],
        *,
        timeout: int = 90,
        workdir: Optional[str | Path] = None,
    ) -> HarnessResult:
        """
        Executa harness com flag --json inserida automaticamente antes dos args.
        Garante que o output seja JSON estruturado para consumo por agentes.
        """
        return await self.run(
            harness_name,
            ["--json"] + list(args),
            timeout=timeout,
            workdir=workdir,
        )

    async def _persist_result(self, result: HarnessResult) -> None:
        """
        Persiste resultado em disco de forma não-bloqueante para rastreabilidade.
        Falha silenciosamente — nunca interrompe o fluxo principal.
        """
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = RESULTS_PATH / f"{result.harness}_{ts}.json"
            content = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, path.write_text, content)
        except Exception as exc:
            logger.warning(f"CLIHarnessAdapter: não foi possível persistir resultado: {exc}")


# ── Singleton thread-safe ────────────────────────────────────────────────────

_adapter_singleton: Optional[CLIHarnessAdapter] = None


def get_harness_adapter() -> CLIHarnessAdapter:
    """
    Retorna instância singleton do CLIHarnessAdapter.
    Inicialização lazy — carrega registry na primeira chamada.
    """
    global _adapter_singleton
    if _adapter_singleton is None:
        _adapter_singleton = CLIHarnessAdapter()
    return _adapter_singleton
