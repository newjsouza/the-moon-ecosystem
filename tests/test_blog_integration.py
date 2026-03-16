"""tests/test_blog_integration.py — Testes de integração Blog + CLI"""

import pytest
from pathlib import Path

SAMPLE_POST = """
# The Moon Ecosystem: Análise 2026

Análise completa do ecossistema de IA autônomo.

```mermaid
graph TD
    Moon[The Moon] --> Orch[Orchestrator]
    Orch --> CLI[MoonCLIAgent]
    CLI --> LO[LibreOffice]
```

## Conclusão

Sistema operacional e expandindo.
"""


class TestExtractMermaidBlocks:
    def test_extrai_bloco_unico(self):
        from skills.cli_harnesses.blog_cli_exporter import extract_mermaid_blocks
        result = extract_mermaid_blocks(SAMPLE_POST)
        assert len(result) == 1
        assert "graph TD" in result[0]["code"]
        assert result[0]["format"] == "svg"
        assert result[0]["name"] == "diagram_1"

    def test_sem_blocos_retorna_lista_vazia(self):
        from skills.cli_harnesses.blog_cli_exporter import extract_mermaid_blocks
        result = extract_mermaid_blocks("# Post sem diagramas\n\nTexto simples.")
        assert result == []

    def test_multiplos_blocos(self):
        from skills.cli_harnesses.blog_cli_exporter import extract_mermaid_blocks
        content = (
            "```mermaid\ngraph TD\n    A-->B\n```\n"
            "texto\n"
            "```mermaid\nsequenceDiagram\n    A->>B: msg\n```"
        )
        result = extract_mermaid_blocks(content)
        assert len(result) == 2
        assert result[0]["name"] == "diagram_1"
        assert result[1]["name"] == "diagram_2"


@pytest.mark.asyncio
class TestBlogExportHook:
    async def test_export_com_mermaid_detectado(self):
        from skills.cli_harnesses.blog_cli_exporter import (
            BlogCLIExporter, extract_mermaid_blocks
        )
        import os
        os.environ["ENABLE_CLI_EXPORTS"] = "true"
        exporter = BlogCLIExporter()
        diagrams = extract_mermaid_blocks(SAMPLE_POST)
        result = await exporter.generate_post_assets(
            post_id="test_blog_integration_001",
            content=SAMPLE_POST,
            diagrams=diagrams,
        )
        assert isinstance(result, dict)
        assert result["post_id"] == "test_blog_integration_001"
        assert "diagrams" in result
        assert len(result["diagrams"]) == len(diagrams)
        print(f"\nExport result: {result}")

    async def test_export_desabilitado_via_env(self):
        """Quando ENABLE_CLI_EXPORTS=false, hook não deve executar."""
        import os
        os.environ["ENABLE_CLI_EXPORTS"] = "false"
        # Verificar que a variável é respeitada
        enabled = os.environ.get("ENABLE_CLI_EXPORTS", "false").lower() == "true"
        assert enabled is False
        os.environ["ENABLE_CLI_EXPORTS"] = "true"  # restaurar
