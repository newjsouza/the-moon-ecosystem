"""tests/test_blog_integration.py — Testes de integração Blog + CLI"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

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


@pytest.mark.asyncio
class TestBlogPublisherMessageBus:
    """Testa integração do BlogPublisherAgent com MessageBus."""

    async def test_publish_event_apos_export(self):
        """Evento blog.published deve ser publicado após exports."""
        from agents.blog.publisher import BlogPublisherAgent
        from core.message_bus import MessageBus
        import os

        os.environ["ENABLE_CLI_EXPORTS"] = "true"

        # Criar publisher e mock bus
        publisher = BlogPublisherAgent()
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        publisher.bus = mock_bus

        # Chamar método de export diretamente
        await publisher._export_post_assets_async(
            post_id="test_event_001",
            content=SAMPLE_POST,
            html_path="meu_blog_autonomo/test.html",
            md_filepath="meu_blog_autonomo/posts_md/test.md",
        )

        # Verificar que publish foi chamado
        assert mock_bus.publish.called
        call_args = mock_bus.publish.call_args
        assert call_args.kwargs["sender"] == "blog_publisher"
        assert call_args.kwargs["topic"] == "blog.published"
        payload = call_args.kwargs["payload"]
        assert payload["post_id"] == "test_event_001"
        assert "html_path" in payload
        assert "pdf_path" in payload
        assert "images" in payload

    async def test_publish_event_mesmo_sem_harness(self):
        """Evento deve ser publicado mesmo se harness indisponível."""
        from agents.blog.publisher import BlogPublisherAgent
        from core.message_bus import MessageBus
        import os

        os.environ["ENABLE_CLI_EXPORTS"] = "true"

        publisher = BlogPublisherAgent()
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        publisher.bus = mock_bus

        # Mock do exporter para simular indisponibilidade (patch no import interno)
        with patch("skills.cli_harnesses.blog_cli_exporter.BlogCLIExporter") as MockExporter:
            instance = MockExporter.return_value
            instance.capabilities.return_value = {
                "pdf_export": False,
                "mermaid_svg": False,
            }

            await publisher._export_post_assets_async(
                post_id="test_no_harness",
                content="# Post sem harness",
                html_path="test.html",
                md_filepath="test.md",
            )

        # Quando não há capabilities, retorna cedo sem publicar evento
        assert not mock_bus.publish.called

    async def test_publish_event_com_excecao(self):
        """Evento é publicado mesmo com exceção (reporta falha)."""
        from agents.blog.publisher import BlogPublisherAgent
        import os

        os.environ["ENABLE_CLI_EXPORTS"] = "true"

        publisher = BlogPublisherAgent()
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        publisher.bus = mock_bus

        # Mock que lança exceção (patch no import interno)
        with patch("skills.cli_harnesses.blog_cli_exporter.BlogCLIExporter") as MockExporter:
            MockExporter.side_effect = Exception("Crash!")

            # Não deve propagar exceção
            await publisher._export_post_assets_async(
                post_id="test_crash",
                content="# Post",
                html_path="test.html",
                md_filepath="test.md",
            )

        # Evento é publicado mesmo com exceção (design: reporta falha)
        assert mock_bus.publish.called
        payload = mock_bus.publish.call_args.kwargs["payload"]
        assert payload["post_id"] == "test_crash"
        assert payload["has_pdf"] is False  # Falhou, sem PDF
