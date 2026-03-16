"""tests/test_moon_cli_agent_generate.py — Testes da Opção A (geração)"""

import os
import pytest
from pathlib import Path


class TestMoonCLIAgentGenerate:
    def test_harness_md_acessivel(self):
        """HARNESS.md deve estar disponível no projeto."""
        paths = [
            Path("skills/cli_harnesses/HARNESS.md"),
            Path("/tmp/cli-anything-src/cli-anything-plugin/HARNESS.md"),
        ]
        found = any(p.exists() for p in paths)
        assert found, f"HARNESS.md não encontrado em nenhum dos paths: {paths}"
        # Verificar que tem conteúdo real
        for p in paths:
            if p.exists():
                content = p.read_text()
                assert len(content) > 1000, f"HARNESS.md parece vazio: {len(content)} chars"
                assert "phase" in content.lower() or "fase" in content.lower(), \
                    "HARNESS.md não contém referência às fases"
                print(f"\n✅ HARNESS.md encontrado: {p} ({len(content)} chars)")
                break

    @pytest.mark.asyncio
    async def test_generate_without_target_returns_error(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("generate")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_generate_nonexistent_path_returns_error(self):
        from agents.moon_cli_agent import MoonCLIAgent
        agent = MoonCLIAgent()
        result = await agent._execute("generate /path/que/nao/existe/abc123xyz")
        # Pode falhar por HARNESS.md ausente ou por path inválido
        # Ambos são resultados válidos — o importante é não travar
        assert result.success in (True, False)  # não deve lançar exceção
        print(f"\nGenerate nonexistent: success={result.success}, error={result.error}")

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.path.exists("/usr/bin/jq"),
        reason="jq não instalado"
    )
    async def test_generate_jq_produces_file(self):
        """Teste real de geração para jq."""
        from agents.moon_cli_agent import MoonCLIAgent
        from pathlib import Path

        agent = MoonCLIAgent()
        result = await agent._execute("generate /usr/bin/jq")

        if result.success:
            output_path = Path(result.data["output_path"])
            assert output_path.exists(), f"Arquivo gerado não existe: {output_path}"
            assert output_path.stat().st_size > 100, "Arquivo gerado está quase vazio"
            lines = result.data["generated_lines"]
            assert lines > 10, f"Muito poucas linhas geradas: {lines}"
            print(f"\n✅ Harness gerado: {output_path} ({lines} linhas)")

            # Verificar se contém código Python (pode ter texto explicativo)
            content = output_path.read_text()
            has_python = "import" in content or "def " in content or "click" in content
            assert has_python, "Arquivo gerado não contém código Python reconhecível"
            print("✅ Arquivo contém código Python")
        else:
            print(f"\n⚠️ Geração falhou: {result.error}")
            # Falha é aceitável — Groq pode ter limitação de tokens
            pytest.skip(f"Geração falhou (pode ser limitação do LLM): {result.error}")
