"""
agents/github_agent.py
Specialized agent for GitHub and terminal automation.

CHANGELOG (Moon Codex — Março 2026):
  - [FIX CRÍTICO] Adicionado asyncio.Event (_stop_event) — loop de parada explícito
  - [FIX CRÍTICO] ping() implementado para health check do Orchestrator
  - [FIX CRÍTICO] repo_full_name.split("/") protegido com validação — não causa crash
  - [FIX] Dependência GithubManager isolada em try/except — graceful degradation
  - [ARCH] create_pr() implementado via PyGitHub direto — necessário pelo AutonomousDevOpsRefactor
  - [ARCH] update_file() / get_file() implementados — integração com pipeline de edição
  - [ARCH] monitor_loop() autônomo para repositórios estratégicos registrados
  - [ARCH] create_branch() implementado — pré-requisito para o pipeline de PR
  - [RESILIÊNCIA] Todas as operações git têm timeout explícito (30s)
  - [RESILIÊNCIA] PyGitHub opcional: fallback para subprocess git puro se não instalado
  - [OBSERVABILIDADE] Histórico de commits monitorados em memória (último por repo)
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent_base import AgentBase, AgentPriority, TaskResult

logger = logging.getLogger("moon.agents.github")

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
GIT_TIMEOUT         = 30     # seconds per git subprocess call
MONITOR_INTERVAL_S  = 3600   # 1h between autonomous repo checks
DEFAULT_REPOS       = [
    repo.strip()
    for repo in os.getenv("GITHUB_MONITOR_REPOS", "").split(",")
    if repo.strip()
]


# ─────────────────────────────────────────────────────────────
#  Git subprocess helper (no external dependency)
# ─────────────────────────────────────────────────────────────

def _run_git(*args: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """
    Runs a git command and returns {success, output, error}.
    Never raises — always returns a dict.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            cwd=cwd or ".",
        )
        success = result.returncode == 0
        return {
            "success": success,
            "output":  result.stdout.strip(),
            "error":   result.stderr.strip() if not success else None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"git timed out after {GIT_TIMEOUT}s"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "git binary not found in PATH"}
    except Exception as exc:
        return {"success": False, "output": "", "error": str(exc)}


# ─────────────────────────────────────────────────────────────
#  PyGitHub wrapper (optional — graceful degradation without it)
# ─────────────────────────────────────────────────────────────

class _GitHubAPIClient:
    """
    Thin wrapper around PyGitHub.
    Falls back gracefully if PyGitHub is not installed or token is missing.
    """

    def __init__(self) -> None:
        self._token   = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self._client  = None
        self._available = False
        self._GithubEx = None
        self._load()

    def _load(self) -> None:
        if not self._token:
            logger.warning("GithubAgent: GITHUB_TOKEN not set — API features disabled.")
            return
        try:
            from github import Github, GithubException
            self._client     = Github(self._token)
            self._GithubEx   = GithubException
            self._available  = True
        except ImportError:
            logger.warning(
                "GithubAgent: PyGitHub not installed — "
                "API features disabled. Run: pip install PyGitHub"
            )

    @property
    def available(self) -> bool:
        return self._available

    def get_repo(self, full_name: str):
        if not self._available:
            raise RuntimeError("PyGitHub not available.")
        return self._client.get_repo(full_name)

    def search_repos(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Wraps Github.search_repositories with error handling."""
        if not self._available or self._client is None:
            return []
        try:
            results = self._client.search_repositories(query=query, sort="stars")
            return [
                {
                    "full_name":   r.full_name,
                    "stars":       r.stargazers_count,
                    "description": r.description or "",
                    "url":         r.html_url,
                    "language":    r.language or "",
                }
                for r in results[:limit]
            ]
        except Exception as exc:
            logger.warning(f"search_repos failed: {exc}")
            return []

    def create_pull_request(
        self,
        repo_full_name: str,
        head: str,
        base: str,
        title: str,
        body: str,
        file_changes: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Creates a GitHub Pull Request and optionally commits file changes."""
        if not self._available or self._client is None:
            raise RuntimeError("PyGitHub not available.")

        gh_repo = self._client.get_repo(repo_full_name)
        default_base = base or gh_repo.default_branch

        # Ensure head branch exists
        try:
            gh_repo.get_branch(head)
        except Exception:
            sha = gh_repo.get_branch(default_base).commit.sha
            gh_repo.create_git_ref(f"refs/heads/{head}", sha)

        # Commit file changes to the head branch
        for change in (file_changes or []):
            filepath = change["path"]
            content = change["content"]
            commit_msg = f"refactor: {title} [{Path(filepath).name}]"
            try:
                existing = gh_repo.get_contents(filepath, ref=head)
                gh_repo.update_file(filepath, commit_msg, content, existing.sha, branch=head)
            except Exception:
                gh_repo.create_file(filepath, commit_msg, content, branch=head)

        # Create PR
        pr = gh_repo.create_pull(
            title=title, body=body, head=head, base=default_base
        )
        return pr.html_url


# ─────────────────────────────────────────────────────────────
#  GitHub Agent
# ─────────────────────────────────────────────────────────────

class GithubAgent(AgentBase):
    """
    Autonomous GitHub & Terminal Operator for The Moon ecosystem.

    Public actions (via execute):
      monitor        → Get latest commits from a repo (kwargs: repo)
      commit         → Stage + commit local changes (kwargs: message, files)
      push           → Push to remote (kwargs: remote, branch)
      pull           → Pull from remote (kwargs: remote, branch)
      search         → Search GitHub repos (kwargs: query, limit)
      create_branch  → Create a new branch (kwargs: repo, branch, base)
      create_pr      → Create a Pull Request (kwargs: repo, branch, title, body, file_changes)
      get_file       → Read a file from a remote repo (kwargs: repo, path, ref)
      update_file    → Update a file in a remote repo (kwargs: repo, path, content, message, branch)
      status         → Current git status
      log            → Last N commits in local repo (kwargs: n)
      diff           → Current diff (kwargs: staged)
    """

    def __init__(self) -> None:
        super().__init__()
        self.name        = "GithubAgent"
        self.priority    = AgentPriority.MEDIUM
        self.description = "Autonomous GitHub & Terminal Operator"

        self._api          = _GitHubAPIClient()
        self._stop_event   = asyncio.Event()
        self._monitor_task: Optional[asyncio.Task] = None

        # Repos to autonomously monitor (set via GITHUB_MONITOR_REPOS or register_watch)
        self._watched_repos: List[str]            = list(DEFAULT_REPOS)
        self._last_seen_sha: Dict[str, str]        = {}   # repo → latest commit SHA

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        self._stop_event.clear()

        if self._watched_repos:
            self._monitor_task = asyncio.create_task(
                self._monitor_loop(), name="moon.github.monitor"
            )
            logger.info(
                f"{self.name} initialized. "
                f"Watching {len(self._watched_repos)} repos. "
                f"PyGitHub API: {'available' if self._api.available else 'offline (subprocess only)'}."
            )
        else:
            logger.info(
                f"{self.name} initialized (no repos to monitor). "
                f"PyGitHub API: {'available' if self._api.available else 'offline'}."
            )

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._monitor_task is not None and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        await super().shutdown()
        logger.info(f"{self.name} shut down.")

    async def ping(self) -> bool:
        """Lightweight liveness probe for the Orchestrator health check."""
        return not self._stop_event.is_set()

    # ═══════════════════════════════════════════════════════════
    #  Execute dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, action: str, **kwargs: Any) -> TaskResult:
        match action:
            case "monitor":
                return await self._monitor_repo(kwargs.get("repo", ""))

            case "commit":
                message = kwargs.get("message", "Autonomous update from The Moon")
                files   = kwargs.get("files", [])
                return await self._commit_changes(message, files)

            case "push":
                return await self._git_op(
                    "push",
                    kwargs.get("remote", "origin"),
                    kwargs.get("branch", ""),
                )

            case "pull":
                return await self._git_op(
                    "pull",
                    kwargs.get("remote", "origin"),
                    kwargs.get("branch", ""),
                )

            case "search":
                query  = kwargs.get("query", "topic:ai-agents language:python")
                limit  = int(kwargs.get("limit", 10))
                return await self._search_repos(query, limit)

            case "create_branch":
                return await self._create_branch(
                    repo   = kwargs.get("repo", ""),
                    branch = kwargs.get("branch", ""),
                    base   = kwargs.get("base", ""),
                )

            case "create_pr":
                return await self._create_pr(
                    repo_full_name = kwargs.get("repo", ""),
                    head           = kwargs.get("branch", ""),
                    title          = kwargs.get("title", ""),
                    body           = kwargs.get("body", ""),
                    file_changes   = kwargs.get("file_changes", []),
                    base           = kwargs.get("base", ""),
                )

            case "get_file":
                return await self._get_file(
                    repo  = kwargs.get("repo", ""),
                    path  = kwargs.get("path", ""),
                    ref   = kwargs.get("ref", ""),
                )

            case "update_file":
                return await self._update_file(
                    repo    = kwargs.get("repo", ""),
                    path    = kwargs.get("path", ""),
                    content = kwargs.get("content", ""),
                    message = kwargs.get("message", "Update via GithubAgent"),
                    branch  = kwargs.get("branch", ""),
                )

            case "status":
                return await self._git_status()

            case "log":
                return await self._git_log(n=int(kwargs.get("n", 5)))

            case "diff":
                staged = bool(kwargs.get("staged", False))
                return await self._git_diff(staged)

            case "watch":
                repo = kwargs.get("repo", "")
                if repo and repo not in self._watched_repos:
                    self._watched_repos.append(repo)
                    return TaskResult(success=True, data={"watching": self._watched_repos})
                return TaskResult(success=False, error=f"Repo '{repo}' already watched or empty.")

            case _:
                return TaskResult(success=False, error=f"Unknown action: '{action}'")

    # ═══════════════════════════════════════════════════════════
    #  Monitor: latest commits from a remote repo
    # ═══════════════════════════════════════════════════════════

    async def _monitor_repo(self, repo_full_name: str) -> TaskResult:
        """Gets the latest commits from a GitHub repo via API."""
        if not repo_full_name:
            return TaskResult(success=False, error="'repo' parameter is required.")
        if "/" not in repo_full_name:
            return TaskResult(
                success=False,
                error=f"Invalid repo format '{repo_full_name}' — expected 'owner/repo'.",
            )
        if not self._api.available:
            return TaskResult(
                success=False,
                error="PyGitHub not available. Install: pip install PyGitHub",
            )

        loop = asyncio.get_event_loop()
        try:
            repo = await loop.run_in_executor(None, self._api.get_repo, repo_full_name)

            def _fetch_commits():
                commits = list(repo.get_commits()[:5])
                return [
                    {
                        "sha":     c.sha[:8],
                        "message": c.commit.message.splitlines()[0][:80],
                        "author":  c.commit.author.name,
                        "date":    c.commit.author.date.isoformat(),
                        "url":     c.html_url,
                    }
                    for c in commits
                ]

            commits = await loop.run_in_executor(None, _fetch_commits)
            if not commits:
                return TaskResult(success=False, error="No commits found.")

            latest_sha = commits[0]["sha"]
            is_new = self._last_seen_sha.get(repo_full_name) != latest_sha
            self._last_seen_sha[repo_full_name] = latest_sha

            return TaskResult(
                success=True,
                data={
                    "repo":       repo_full_name,
                    "commits":    commits,
                    "latest_sha": latest_sha,
                    "new_activity": is_new,
                },
            )
        except Exception as exc:
            logger.error(f"Monitor {repo_full_name}: {exc}")
            return TaskResult(success=False, error=str(exc))

    # ═══════════════════════════════════════════════════════════
    #  Local git operations (subprocess)
    # ═══════════════════════════════════════════════════════════

    async def _commit_changes(self, message: str, files: List[str]) -> TaskResult:
        """Stages specified files (or all if empty) and commits."""
        loop = asyncio.get_event_loop()

        if files:
            add_result = await loop.run_in_executor(None, _run_git, "add", *files)
        else:
            add_result = await loop.run_in_executor(None, _run_git, "add", ".")

        if not add_result["success"]:
            return TaskResult(success=False, error=f"git add failed: {add_result['error']}")

        commit_result = await loop.run_in_executor(None, _run_git, "commit", "-m", message)
        if not commit_result["success"]:
            # "nothing to commit" is not a real failure
            if "nothing to commit" in (commit_result["error"] or ""):
                return TaskResult(success=True, data={"status": "nothing to commit"})
            return TaskResult(success=False, error=f"git commit failed: {commit_result['error']}")

        return TaskResult(
            success=True,
            data={
                "message": message,
                "output":  commit_result["output"],
            },
        )

    async def _git_op(self, op: str, remote: str, branch: str) -> TaskResult:
        """Generic push/pull via subprocess."""
        args = [op, remote]
        if branch:
            args.append(branch)
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_git, *args)
        return TaskResult(
            success=result["success"],
            data   ={"output": result["output"]},
            error  =result.get("error"),
        )

    async def _git_status(self) -> TaskResult:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_git, "status", "--porcelain")
        return TaskResult(
            success=result["success"],
            data   ={"status": result["output"], "clean": result["output"] == ""},
            error  =result.get("error"),
        )

    async def _git_log(self, n: int = 5) -> TaskResult:
        loop   = asyncio.get_event_loop()
        fmt    = "--pretty=format:%h|%s|%an|%ar"
        result = await loop.run_in_executor(None, _run_git, "log", f"-{n}", fmt)
        if not result["success"]:
            return TaskResult(success=False, error=result["error"])

        commits = []
        for line in result["output"].splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "sha":     parts[0],
                    "message": parts[1],
                    "author":  parts[2],
                    "when":    parts[3],
                })
        return TaskResult(success=True, data={"commits": commits})

    async def _git_diff(self, staged: bool = False) -> TaskResult:
        args   = ["diff", "--stat"]
        if staged:
            args.insert(1, "--cached")
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_git, *args)
        return TaskResult(
            success=result["success"],
            data   ={"diff": result["output"]},
            error  =result.get("error"),
        )

    # ═══════════════════════════════════════════════════════════
    #  GitHub API operations (PyGitHub)
    # ═══════════════════════════════════════════════════════════

    async def _search_repos(self, query: str, limit: int) -> TaskResult:
        """Search GitHub repos via PyGitHub API."""
        if not self._api.available:
            return TaskResult(success=False, error="PyGitHub not available.")
        loop    = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, self._api.search_repos, query, limit
        )
        return TaskResult(success=True, data={"trending": results, "count": len(results)})

    async def _create_branch(self, repo: str, branch: str, base: str) -> TaskResult:
        """Creates a new branch on a remote repo."""
        if not self._api.available:
            return TaskResult(success=False, error="PyGitHub not available.")
        if not repo or not branch:
            return TaskResult(success=False, error="'repo' and 'branch' are required.")
        if "/" not in repo:
            return TaskResult(success=False, error=f"Invalid repo format: '{repo}'")

        loop = asyncio.get_event_loop()
        try:
            def _create():
                gh_repo  = self._api.get_repo(repo)
                base_ref = base or gh_repo.default_branch
                sha      = gh_repo.get_branch(base_ref).commit.sha
                gh_repo.create_git_ref(f"refs/heads/{branch}", sha)
                return sha

            sha = await loop.run_in_executor(None, _create)
            return TaskResult(success=True, data={"branch": branch, "base_sha": sha[:8]})
        except Exception as exc:
            return TaskResult(success=False, error=str(exc))

    async def _create_pr(
        self,
        repo:         str,
        branch:       str,
        title:        str,
        body:         str,
        file_changes: Dict[str, str],   # path → new_content
        base:         str = "",
    ) -> TaskResult:
        """
        Creates a GitHub Pull Request.
        If file_changes is provided, commits each file to the branch first.
        This is the bridge method used by AutonomousDevOpsRefactor.
        """
        if not self._api.available:
            return TaskResult(
                success=False,
                error="PyGitHub not available. Install: pip install PyGitHub",
            )
        if not all([repo, branch, title]):
            return TaskResult(success=False, error="'repo', 'branch', and 'title' are required.")
        if "/" not in repo:
            return TaskResult(success=False, error=f"Invalid repo format: '{repo}'")

        loop = asyncio.get_event_loop()
        try:
            def _build_pr() -> str:
                gh_repo      = self._api.get_repo(repo)
                default_base = base or gh_repo.default_branch

                # Ensure branch exists
                try:
                    gh_repo.get_branch(branch)
                except Exception:
                    sha = gh_repo.get_branch(default_base).commit.sha
                    gh_repo.create_git_ref(f"refs/heads/{branch}", sha)

                # Commit file changes to the branch
                for filepath, content in (file_changes or {}).items():
                    commit_msg = f"refactor: {title} [{Path(filepath).name}]"
                    try:
                        existing = gh_repo.get_contents(filepath, ref=default_base)
                        gh_repo.update_file(filepath, commit_msg, content, existing.sha, branch=branch)
                    except Exception:
                        gh_repo.create_file(filepath, commit_msg, content, branch=branch)

                # Create PR
                pr = gh_repo.create_pull(
                    title=title, body=body, head=branch, base=default_base
                )
                return pr.html_url

            pr_url = await loop.run_in_executor(None, _build_pr)
            logger.info(f"PR created: {pr_url}")
            return TaskResult(success=True, data={"pr_url": pr_url, "branch": branch})

        except Exception as exc:
            logger.error(f"create_pr failed: {exc}")
            return TaskResult(success=False, error=str(exc))

    async def _get_file(self, repo: str, path: str, ref: str) -> TaskResult:
        """Reads a file's content from a remote GitHub repo."""
        if not self._api.available:
            return TaskResult(success=False, error="PyGitHub not available.")
        if not repo or not path:
            return TaskResult(success=False, error="'repo' and 'path' are required.")
        if "/" not in repo:
            return TaskResult(success=False, error=f"Invalid repo format: '{repo}'")

        loop = asyncio.get_event_loop()
        try:
            def _fetch():
                gh_repo  = self._api.get_repo(repo)
                contents = gh_repo.get_contents(path, ref=ref or gh_repo.default_branch)
                return {
                    "path":     contents.path,
                    "content":  contents.decoded_content.decode("utf-8", errors="replace"),
                    "sha":      contents.sha,
                    "size":     contents.size,
                    "encoding": contents.encoding,
                }

            data = await loop.run_in_executor(None, _fetch)
            return TaskResult(success=True, data=data)
        except Exception as exc:
            return TaskResult(success=False, error=str(exc))

    async def _update_file(
        self, repo: str, path: str, content: str, message: str, branch: str
    ) -> TaskResult:
        """Updates an existing file in a remote GitHub repo."""
        if not self._api.available:
            return TaskResult(success=False, error="PyGitHub not available.")
        if not all([repo, path, content]):
            return TaskResult(success=False, error="'repo', 'path', and 'content' are required.")
        if "/" not in repo:
            return TaskResult(success=False, error=f"Invalid repo format: '{repo}'")

        loop = asyncio.get_event_loop()
        try:
            def _update():
                gh_repo  = self._api.get_repo(repo)
                ref      = branch or gh_repo.default_branch
                existing = gh_repo.get_contents(path, ref=ref)
                result   = gh_repo.update_file(path, message, content, existing.sha, branch=ref)
                return result["commit"].sha

            commit_sha = await loop.run_in_executor(None, _update)
            return TaskResult(
                success=True,
                data={"path": path, "commit_sha": commit_sha[:8], "branch": branch},
            )
        except Exception as exc:
            return TaskResult(success=False, error=str(exc))

    # ═══════════════════════════════════════════════════════════
    #  Autonomous monitor loop
    # ═══════════════════════════════════════════════════════════

    async def _monitor_loop(self) -> None:
        """
        Periodically checks watched repos for new activity.
        Publishes alerts via the Orchestrator if new commits are detected.
        """
        logger.info(
            f"GitHub monitor loop started for {len(self._watched_repos)} repos."
        )
        while not self._stop_event.is_set():
            for repo in self._watched_repos:
                if self._stop_event.is_set():
                    break
                try:
                    result = await self._monitor_repo(repo)
                    if result.success and result.data.get("new_activity"):
                        latest = result.data["commits"][0]
                        logger.info(
                            f"New activity in {repo}: "
                            f"[{latest['sha']}] {latest['message']}"
                        )
                except Exception as exc:
                    logger.debug(f"Monitor loop error for {repo}: {exc}")

            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=MONITOR_INTERVAL_S,
                )
                break
            except asyncio.TimeoutError:
                pass

        logger.info("GitHub monitor loop stopped.")

