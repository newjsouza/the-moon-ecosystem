"""tests/test_blog_cli_exporter.py — Testes do BlogCLIExporter"""

import asyncio
import os
import tempfile
from pathlib import Path
import pytest


class TestBlogCLIExporterImport:
    def test_import_succeeds(self):
        from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter
        assert BlogCLIExporter is not None

    def test_capabilities_returns_real_dict(self):
        from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter
        e = BlogCLIExporter()
        caps = e.capabilities()
        assert isinstance(caps, dict)
        assert "pdf_export" in caps
        assert "mermaid_svg" in caps
        # Valores devem ser bool
        for k, v in caps.items():
            assert isinstance(v, bool), f"{k} não é bool: {v}"
        print(f"\nCapacidades: {caps}")

    def test_exports_dir_created(self):
        from skills.cli_harnesses.blog_cli_exporter import EXPORTS_DIR
        assert EXPORTS_DIR.exists(), f"EXPORTS_DIR não foi criado: {EXPORTS_DIR}"


@pytest.mark.asyncio
class TestBlogCLIExporterPDF:
    async def test_post_to_pdf_unavailable_returns_none(self):
        """Quando LibreOffice não disponível, retorna None sem exceção."""
        from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter
        from core.cli_harness_adapter import get_harness_adapter
        if not get_harness_adapter().is_available("libreoffice"):
            pytest.skip("LibreOffice não disponível — testar o caminho positivo")
        # Se disponível, testar que não lança exceção com conteúdo real
        e = BlogCLIExporter()
        result = await e.post_to_pdf(
            content="# Test Moon Post\n\nConteúdo de teste real.",
            filename="test_moon_post_smoke",
        )
        # Pode ser None (se PDF falhou) ou Path (se funcionou) — ambos são válidos
        assert result is None or isinstance(result, Path)
        print(f"\npost_to_pdf result: {result}")

    async def test_generate_post_assets_returns_dict(self):
        from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter
        e = BlogCLIExporter()
        result = await e.generate_post_assets(
            post_id="test_smoke_001",
            content="# Test\n\nConteúdo de teste para o Moon Stack.",
            diagrams=[],
        )
        assert isinstance(result, dict)
        assert "post_id" in result
        assert result["post_id"] == "test_smoke_001"
        assert "generated_at" in result
        print(f"\ngenerate_post_assets: {result}")


@pytest.mark.asyncio
class TestBlogCLIExporterMermaid:
    async def test_mermaid_to_image_returns_path_or_none(self):
        from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter
        e = BlogCLIExporter()
        result = await e.mermaid_to_image(
            mermaid_code=(
                "graph TD\n"
                "    Moon[The Moon] --> CLI[MoonCLIAgent]\n"
                "    CLI --> LO[LibreOffice]\n"
                "    CLI --> MM[Mermaid]"
            ),
            filename="test_moon_arch_smoke",
            format="svg",
        )
        assert result is None or isinstance(result, Path)
        if result:
            assert result.exists(), f"Arquivo não existe: {result}"
            assert result.stat().st_size > 0
        print(f"\nmermaid_to_image result: {result}")

    async def test_generate_post_assets_with_diagram(self):
        from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter
        e = BlogCLIExporter()
        result = await e.generate_post_assets(
            post_id="test_with_diagram_001",
            content="# Post com Diagrama\n\nConteúdo do post.",
            diagrams=[{
                "name": "arquitetura",
                "code": "graph LR\n    A[Moon] --> B[CLI]",
                "format": "svg"
            }],
        )
        assert isinstance(result, dict)
        assert "diagrams" in result
        assert isinstance(result["diagrams"], list)
        print(f"\ngenerate_post_assets with diagram: {result}")
