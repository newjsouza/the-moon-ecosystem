"""tests/test_cli_harness_adapter.py — Testes do CLIHarnessAdapter"""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest


class TestCLIHarnessAdapterImport:
    def test_imports_succeed(self):
        from core.cli_harness_adapter import (
            CLIHarnessAdapter,
            HarnessResult,
            get_harness_adapter,
        )
        assert CLIHarnessAdapter is not None
        assert HarnessResult is not None
        assert get_harness_adapter is not None


class TestCLIHarnessAdapterRegistry:
    def test_loads_real_registry(self):
        from core.cli_harness_adapter import CLIHarnessAdapter
        adapter = CLIHarnessAdapter()
        registry_path = Path("skills/cli_harnesses/installed_harnesses.json")
        if not registry_path.exists():
            pytest.skip("Registry não criado — executar Fase 1 primeiro")
        with open(registry_path) as f:
            data = json.load(f)
        installed = [h for h in data["harnesses"] if h["installed"] and not h.get("skipped")]
        for h in installed:
            assert adapter.is_available(h["name"]), (
                f"Harness {h['name']} está no registry como installed=True mas "
                f"is_available() retornou False (binário não encontrado no PATH)"
            )

    def test_unavailable_harness_returns_false(self):
        from core.cli_harness_adapter import CLIHarnessAdapter
        adapter = CLIHarnessAdapter()
        assert adapter.is_available("harness_que_nao_existe_xyz_abc_123") is False

    def test_list_available_all_have_binary(self):
        from core.cli_harness_adapter import CLIHarnessAdapter
        adapter = CLIHarnessAdapter()
        available = adapter.list_available()
        for h in available:
            binary_path = shutil.which(h["binary"])
            assert binary_path is not None, (
                f"list_available() incluiu '{h['binary']}' mas shutil.which retornou None"
            )


@pytest.mark.asyncio
class TestCLIHarnessAdapterRun:
    async def test_run_unavailable_returns_failure(self):
        from core.cli_harness_adapter import get_harness_adapter
        adapter = get_harness_adapter()
        result = await adapter.run("harness_inexistente_abc123", ["--help"])
        assert result.success is False
        assert result.exit_code == -1
        assert result.harness == "harness_inexistente_abc123"
        assert result.raw_stderr != ""

    async def test_run_real_harness_help(self):
        from core.cli_harness_adapter import get_harness_adapter
        adapter = get_harness_adapter()
        available = adapter.list_available()
        if not available:
            pytest.skip("Nenhum harness instalado")
        harness_name = available[0]["name"]
        result = await adapter.run(harness_name, ["--help"])
        assert result.exit_code == 0, (
            f"'{harness_name} --help' retornou exit {result.exit_code}: {result.raw_stderr[:200]}"
        )
        assert len(result.raw_stdout) > 10, "stdout do --help está vazio"
        assert result.harness == harness_name
        assert result.duration_ms > 0

    async def test_run_json_prepends_json_flag(self):
        from core.cli_harness_adapter import get_harness_adapter
        adapter = get_harness_adapter()
        available = adapter.list_available()
        if not available:
            pytest.skip("Nenhum harness instalado")
        harness_name = available[0]["name"]
        result = await adapter.run_json(harness_name, ["--help"])
        # --json + --help pode dar exit != 0 dependendo do harness, mas
        # o comando deve ter sido construído com --json no início
        assert "--json" in result.command
        assert result.command.index("--json") == 1  # [binary, "--json", "--help"]

    async def test_persists_result_to_disk(self):
        from core.cli_harness_adapter import get_harness_adapter
        import glob
        adapter = get_harness_adapter()
        available = adapter.list_available()
        if not available:
            pytest.skip("Nenhum harness instalado")
        harness_name = available[0]["name"]
        before = set(glob.glob("data/cli_harness_results/*.json"))
        await adapter.run(harness_name, ["--help"])
        after = set(glob.glob("data/cli_harness_results/*.json"))
        new_files = after - before
        assert len(new_files) >= 1, "Nenhum arquivo de resultado salvo em disco"
        newest = list(new_files)[0]
        with open(newest) as f:
            saved = json.load(f)
        assert saved["harness"] == harness_name
        assert "timestamp" in saved
        assert "exit_code" in saved
