"""tests/test_moon_cli_agent.py — Testes do MoonCLIAgent"""

import pytest
from tests.conftest import requires_libreoffice, requires_mermaid


class TestMoonCLIAgentImport:
    def test_import_succeeds(self):
        from agents.moon_cli_agent import MoonCLIAgent
        assert MoonCLIAgent is not None

    def test_routing_keywords_exist(self):
        from agents.moon_cli_agent import MoonCLIAgent
        assert hasattr(MoonCLIAgent, "ROUTING_KEYWORDS")
        assert len(MoonCLIAgent.ROUTING_KEYWORDS) > 0
        assert "cli" in MoonCLIAgent.ROUTING_KEYWORDS
        assert "libreoffice" in MoonCLIAgent.ROUTING_KEYWORDS


@pytest.mark.asyncio
class TestMoonCLIAgentActions:
    async def test_list_returns_dict_with_harnesses(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("list")
        assert result.success is True
        assert isinstance(result.data, dict)
        assert "harnesses" in result.data
        assert "count" in result.data
        assert isinstance(result.data["count"], int)
        assert result.data["count"] == len(result.data["harnesses"])

    async def test_discover_returns_list(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("discover")
        assert result.success is True
        assert "discovered" in result.data
        assert "count" in result.data
        assert isinstance(result.data["discovered"], list)

    async def test_invalid_action_returns_error(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("acao_invalida_xyz")
        assert result.success is False
        assert result.error is not None
        assert "acao_invalida_xyz" in result.error or "desconhecida" in result.error.lower()

    async def test_empty_task_returns_error(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("")
        assert result.success is False
        assert result.error is not None

    async def test_run_without_harness_name_returns_error(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("run")
        assert result.success is False

    @requires_libreoffice
    async def test_run_real_harness_help(self):
        from agents.moon_cli_agent import MoonCLIAgent
        from core.cli_harness_adapter import get_harness_adapter
        available = get_harness_adapter().list_available()
        if not available:
            pytest.skip("Nenhum harness instalado")
        harness_name = available[0]["name"]
        agent = MoonCLIAgent()
        result = await agent._execute(f"run {harness_name} --help")
        assert result.success is True
        assert result.data["exit_code"] == 0

    @requires_libreoffice
    async def test_help_command_works(self):
        from agents.moon_cli_agent import MoonCLIAgent
        from core.cli_harness_adapter import get_harness_adapter
        available = get_harness_adapter().list_available()
        if not available:
            pytest.skip("Nenhum harness instalado")
        harness_name = available[0]["name"]
        agent = MoonCLIAgent()
        result = await agent._execute(f"help {harness_name}")
        assert result.success is True

    async def test_generate_without_target_returns_error(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("generate")
        assert result.success is False
        assert "obrigatório" in (result.error or "").lower() or "target" in (result.error or "").lower()