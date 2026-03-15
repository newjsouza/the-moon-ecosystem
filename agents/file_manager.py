"""
agents/file_manager.py
File system operations agent — read, write, edit, list, search.
Accessible via Telegram commands.
"""

import os
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FileManagerAgent(AgentBase):
    """Handles file system operations for the Telegram bot."""

    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.CRITICAL
        self.description = "File system operations (read/write/list/search)"
        self.logger = setup_logger("FileManagerAgent")
        self.root = PROJECT_ROOT

    def _resolve_path(self, path_str: str) -> Path:
        """Resolves a path relative to the project root or as absolute."""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return self.root / p

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        action = kwargs.get("action", task)
        path = kwargs.get("path", "")

        if action == "read":
            return await self._read_file(path)
        elif action == "write":
            content = kwargs.get("content", "")
            return await self._write_file(path, content)
        elif action == "ls":
            return await self._list_dir(path or ".")
        elif action == "search":
            query = kwargs.get("query", task)
            return await self._search(query, path)
        elif action == "edit":
            content = kwargs.get("content", "")
            return await self._edit_file(path, content)
        elif action == "tree":
            return await self._tree(path or ".")
        else:
            return TaskResult(success=False, error=f"Unknown action: {action}")

    async def _read_file(self, path_str: str) -> TaskResult:
        """Reads a file and returns its content (truncated for Telegram)."""
        fpath = self._resolve_path(path_str)
        if not fpath.exists():
            return TaskResult(success=False, error=f"File not found: {fpath}")
        if not fpath.is_file():
            return TaskResult(success=False, error=f"Not a file: {fpath}")

        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            total = len(lines)

            # Truncate for Telegram (max ~3500 chars to leave room for formatting)
            if len(content) > 3500:
                content = content[:3500] + f"\n\n... (truncado, {total} linhas total)"

            return TaskResult(success=True, data={
                "content": content,
                "path": str(fpath),
                "lines": total,
                "size": fpath.stat().st_size
            })
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _write_file(self, path_str: str, content: str) -> TaskResult:
        """Writes content to a file."""
        fpath = self._resolve_path(path_str)
        try:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
            return TaskResult(success=True, data={
                "path": str(fpath),
                "size": fpath.stat().st_size,
                "message": f"Written to {fpath.name}"
            })
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _edit_file(self, path_str: str, edit_instruction: str) -> TaskResult:
        """Reads a file, shows it, and prepares for LLM-assisted editing."""
        fpath = self._resolve_path(path_str)
        if not fpath.exists():
            return TaskResult(success=False, error=f"File not found: {fpath}")

        content = fpath.read_text(encoding="utf-8", errors="replace")
        return TaskResult(success=True, data={
            "content": content,
            "path": str(fpath),
            "instruction": edit_instruction,
            "status": "ready_for_edit"
        })

    async def _list_dir(self, path_str: str) -> TaskResult:
        """Lists directory contents."""
        dpath = self._resolve_path(path_str)
        if not dpath.exists():
            return TaskResult(success=False, error=f"Directory not found: {dpath}")
        if not dpath.is_dir():
            return TaskResult(success=False, error=f"Not a directory: {dpath}")

        try:
            entries = []
            for item in sorted(dpath.iterdir()):
                if item.name.startswith(".") and item.name not in (".env",):
                    continue
                icon = "📁" if item.is_dir() else "📄"
                size = ""
                if item.is_file():
                    s = item.stat().st_size
                    size = f" ({s}B)" if s < 1024 else f" ({s//1024}KB)"
                entries.append(f"{icon} {item.name}{size}")

            listing = "\n".join(entries[:50])
            if len(entries) > 50:
                listing += f"\n\n... e mais {len(entries) - 50} itens"

            return TaskResult(success=True, data={
                "listing": listing,
                "path": str(dpath),
                "count": len(entries)
            })
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _search(self, query: str, path_str: str = "") -> TaskResult:
        """Searches for a pattern in the codebase using grep."""
        search_path = self._resolve_path(path_str) if path_str else self.root

        try:
            proc = await asyncio.create_subprocess_exec(
                "grep", "-rnI", "--include=*.py", "--include=*.md",
                "--include=*.yaml", "--include=*.json", "--include=*.txt",
                "-m", "20", query, str(search_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode(errors="replace").strip()

            if not output:
                return TaskResult(success=True, data={
                    "results": "Nenhum resultado encontrado.",
                    "query": query
                })

            # Trim paths to be relative to project root
            lines = output.split("\n")
            results = []
            for line in lines[:20]:
                line = line.replace(str(self.root) + "/", "")
                results.append(line)

            return TaskResult(success=True, data={
                "results": "\n".join(results),
                "query": query,
                "count": len(results)
            })
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def _tree(self, path_str: str) -> TaskResult:
        """Shows a tree view of the project structure."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "find", str(self._resolve_path(path_str)),
                "-maxdepth", "2", "-not", "-path", "*/.git/*",
                "-not", "-path", "*/__pycache__/*",
                "-not", "-path", "*/.venv/*", "-not", "-path", "*/venv/*",
                "-not", "-path", "*/.pytest_cache/*",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode(errors="replace").strip()
            lines = output.split("\n")[:60]

            # Make relative
            tree = []
            for l in lines:
                l = l.replace(str(self.root) + "/", "").replace(str(self.root), ".")
                tree.append(l)

            return TaskResult(success=True, data={
                "tree": "\n".join(tree),
                "count": len(tree)
            })
        except Exception as e:
            return TaskResult(success=False, error=str(e))
