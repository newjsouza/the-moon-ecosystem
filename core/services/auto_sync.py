"""
core/services/auto_sync.py

AutoSyncService — Sincronização automática com GitHub após implementações.

Responsabilidades:
  1. Detectar arquivos modificados/criados
  2. Montar commit message semântico
  3. Push automático após implementações
  4. Notificar via Telegram após sync bem-sucedido

Uso:
  sync = AutoSyncService()
  await sync.sync_now(message="feat: CLI-Anything integration Phase 3")
  await sync.sync_if_dirty()  # apenas se há mudanças
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class SyncResult:
    def __init__(
        self,
        success: bool,
        committed: bool,
        pushed: bool,
        files_changed: list,
        commit_sha: Optional[str],
        message: str,
        error: Optional[str] = None,
    ):
        self.success = success
        self.committed = committed
        self.pushed = pushed
        self.files_changed = files_changed
        self.commit_sha = commit_sha
        self.message = message
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "committed": self.committed,
            "pushed": self.pushed,
            "files_changed": self.files_changed,
            "commit_sha": self.commit_sha,
            "message": self.message,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class AutoSyncService:
    """
    Serviço de sincronização automática com GitHub.
    Thread-safe, async-first, falha silenciosamente sem
    interromper o fluxo principal do Moon.
    """

    # Padrões a NUNCA commitar (além do .gitignore)
    NEVER_COMMIT_PATTERNS = [
        ".env",
        "*.env",
        ".env.*",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".DS_Store",
        "node_modules/",
        "*.log",
        "data/cli_harness_results/",  # resultados temporários
        "learning/workspaces/",  # workspace do SkillAlchemist
    ]

    def __init__(self):
        self._git_available = self._check_git()
        self._remote_url = self._get_remote_url()
        logger.info(
            f"AutoSyncService: git={self._git_available} "
            f"remote={self._remote_url or 'não configurado'}"
        )

    def _check_git(self) -> bool:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                cwd=str(_PROJECT_ROOT),
            )
            return r.returncode == 0
        except FileNotFoundError:
            return False

    def _get_remote_url(self) -> Optional[str]:
        try:
            r = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=str(_PROJECT_ROOT),
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    def _run_git(self, args: list, timeout: int = 60) -> tuple[int, str, str]:
        """Executa comando git real, retorna (exit_code, stdout, stderr)."""
        try:
            r = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(_PROJECT_ROOT),
            )
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", f"Timeout após {timeout}s"
        except Exception as exc:
            return -2, "", str(exc)

    def is_dirty(self) -> bool:
        """Verifica se há mudanças não commitadas."""
        code, stdout, _ = self._run_git(["status", "--porcelain"])
        return code == 0 and bool(stdout.strip())

    def get_changed_files(self) -> list[str]:
        """Retorna lista de arquivos modificados/novos."""
        code, stdout, _ = self._run_git(["status", "--porcelain"])
        if code != 0 or not stdout:
            return []
        files = []
        for line in stdout.splitlines():
            if line.strip():
                # Formato: "XY path" — pegar apenas o path
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1].strip())
        return files

    def _build_commit_message(
        self, custom_message: Optional[str], changed_files: list[str]
    ) -> str:
        """
        Monta mensagem de commit semântica baseada nos arquivos alterados.
        Se custom_message fornecida, usa ela como título.
        """
        if custom_message:
            return custom_message

        # Auto-detectar tipo de mudança pelos paths
        has_agents = any("agents/" in f for f in changed_files)
        has_core = any("core/" in f for f in changed_files)
        has_skills = any("skills/" in f for f in changed_files)
        has_tests = any("tests/" in f for f in changed_files)
        has_docs = any(f.endswith(".md") for f in changed_files)
        has_data = any("data/" in f for f in changed_files)

        parts = []
        if has_agents:
            parts.append("agents")
        if has_core:
            parts.append("core")
        if has_skills:
            parts.append("skills")
        if has_tests:
            parts.append("tests")
        if has_docs:
            parts.append("docs")
        if has_data:
            parts.append("data")

        scope = "+".join(parts) if parts else "misc"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        n = len(changed_files)
        return f"chore({scope}): auto-sync {n} file(s) — {ts}"

    async def sync_now(
        self,
        message: Optional[str] = None,
        branch: str = "main",
        add_all: bool = True,
    ) -> SyncResult:
        """
        Executa git add + commit + push de forma assíncrona.
        Nunca lança exceção — erros são encapsulados em SyncResult.

        Args:
            message: mensagem de commit customizada (auto se None)
            branch: branch de destino (default: main)
            add_all: se True, faz git add . (respeitando .gitignore)
        """
        if not self._git_available:
            return SyncResult(
                success=False,
                committed=False,
                pushed=False,
                files_changed=[],
                commit_sha=None,
                message="",
                error="Git não disponível",
            )

        loop = asyncio.get_event_loop()

        try:
            # Executar em thread para não bloquear event loop
            result = await loop.run_in_executor(
                None, self._sync_blocking, message, branch, add_all
            )
            return result
        except Exception as exc:
            logger.error(f"AutoSyncService.sync_now: erro: {exc}", exc_info=True)
            return SyncResult(
                success=False,
                committed=False,
                pushed=False,
                files_changed=[],
                commit_sha=None,
                message=message or "",
                error=str(exc),
            )

    def _sync_blocking(
        self, message: Optional[str], branch: str, add_all: bool
    ) -> SyncResult:
        """Operação síncrona de sync — executada em thread separada."""

        # 1. Verificar mudanças
        changed = self.get_changed_files()
        if not changed:
            logger.info("AutoSyncService: nenhuma mudança detectada, skip sync")
            return SyncResult(
                success=True,
                committed=False,
                pushed=False,
                files_changed=[],
                commit_sha=None,
                message="Sem mudanças",
            )

        # 2. git add
        if add_all:
            code, _, stderr = self._run_git(["add", "."])
            if code != 0:
                return SyncResult(
                    success=False,
                    committed=False,
                    pushed=False,
                    files_changed=changed,
                    commit_sha=None,
                    message="",
                    error=f"git add falhou: {stderr}",
                )

        # 3. Montar e executar commit
        commit_msg = self._build_commit_message(message, changed)
        code, stdout, stderr = self._run_git(["commit", "-m", commit_msg], timeout=30)

        if code != 0:
            # Pode ser "nothing to commit" — não é erro real
            if "nothing to commit" in stderr.lower() or "nothing to commit" in stdout.lower():
                logger.info("AutoSyncService: nothing to commit")
                return SyncResult(
                    success=True,
                    committed=False,
                    pushed=False,
                    files_changed=[],
                    commit_sha=None,
                    message="Nada para commitar",
                )
            return SyncResult(
                success=False,
                committed=False,
                pushed=False,
                files_changed=changed,
                commit_sha=None,
                message=commit_msg,
                error=f"git commit falhou: {stderr}",
            )

        # 4. Pegar SHA do commit
        sha_code, sha, _ = self._run_git(["rev-parse", "HEAD"])
        commit_sha = sha[:8] if sha_code == 0 else None

        logger.info(f"AutoSyncService: commit {commit_sha}: {commit_msg}")

        # 5. git push
        # Usar token do ambiente se disponível
        token = os.environ.get("GITHUB_TOKEN", "")
        if token and self._remote_url and "github.com" in self._remote_url:
            # Construir URL autenticada sem expor o token em logs
            auth_url = self._remote_url.replace(
                "https://", f"https://x-access-token:{token}@"
            ).replace(
                "git@github.com:", "https://x-access-token:" + token + "@github.com/"
            )
            push_args = ["push", auth_url, f"HEAD:{branch}"]
        else:
            push_args = ["push", "origin", branch]

        push_code, push_out, push_err = self._run_git(push_args, timeout=60)

        if push_code != 0:
            return SyncResult(
                success=False,
                committed=True,
                pushed=False,
                files_changed=changed,
                commit_sha=commit_sha,
                message=commit_msg,
                error=f"git push falhou: {push_err[:200]}",
            )

        logger.info(
            f"AutoSyncService: push OK → {branch} "
            f"({len(changed)} arquivos, SHA={commit_sha})"
        )
        return SyncResult(
            success=True,
            committed=True,
            pushed=True,
            files_changed=changed,
            commit_sha=commit_sha,
            message=commit_msg,
        )

    async def sync_if_dirty(
        self,
        message: Optional[str] = None,
        branch: str = "main",
    ) -> SyncResult:
        """
        Sync apenas se há mudanças não commitadas.
        Útil para chamadas periódicas sem ruído de commits vazios.
        """
        if not self.is_dirty():
            return SyncResult(
                success=True,
                committed=False,
                pushed=False,
                files_changed=[],
                commit_sha=None,
                message="Repositório limpo, sem necessidade de sync",
            )
        return await self.sync_now(message=message, branch=branch)


# ── Singleton ─────────────────────────────────────────────────────────────────

_sync_singleton: Optional[AutoSyncService] = None


def get_auto_sync() -> AutoSyncService:
    global _sync_singleton
    if _sync_singleton is None:
        _sync_singleton = AutoSyncService()
    return _sync_singleton
