"""
skills/cli_harnesses/blog_cli_exporter.py

BlogCLIExporter — Exportador de conteúdo do blog via CLI-Anything harnesses.

Capacidades:
  - Exportar post markdown/texto para PDF via cli-anything-libreoffice
  - Renderizar diagrama Mermaid para SVG/PNG via cli-anything-mermaid
  - Exportar apresentação para PPTX via cli-anything-libreoffice (impress)

Design: módulo standalone, zero dependências do blog agent.
Importado opcionalmente — falha silenciosa se harness não disponível.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Diretório de exports — relativo à raiz do projeto
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORTS_DIR = _PROJECT_ROOT / "data" / "blog_exports"


class BlogCLIExporter:
    """
    Exportador de conteúdo do blog via CLI-Anything harnesses.

    Uso:
        exporter = BlogCLIExporter()

        # Exportar post para PDF
        pdf_path = await exporter.post_to_pdf(
            content="# Título\n\nConteúdo do post...",
            filename="post_titulo_2026.pdf"
        )

        # Renderizar diagrama Mermaid
        img_path = await exporter.mermaid_to_image(
            mermaid_code="graph TD\n    A-->B",
            filename="diagrama_arch",
            format="svg"
        )

        # Verificar disponibilidade
        caps = exporter.capabilities()
        # {"pdf_export": True, "mermaid_render": True}
    """

    def __init__(self):
        from core.cli_harness_adapter import get_harness_adapter
        self._adapter = get_harness_adapter()
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"BlogCLIExporter inicializado. "
            f"Capacidades: {self.capabilities()}"
        )

    def capabilities(self) -> dict:
        """Retorna dicionário com capacidades disponíveis baseado em harnesses reais."""
        return {
            "pdf_export": self._adapter.is_available("libreoffice"),
            "docx_export": self._adapter.is_available("libreoffice"),
            "impress_export": self._adapter.is_available("libreoffice"),
            "mermaid_svg": self._adapter.is_available("mermaid"),
            "mermaid_png": self._adapter.is_available("mermaid"),
        }

    async def post_to_pdf(
        self,
        content: str,
        filename: str,
        output_dir: Optional[Path] = None,
        overwrite: bool = True,
    ) -> Optional[Path]:
        """
        Exporta conteúdo textual/markdown para PDF via cli-anything-libreoffice.

        Pipeline:
          1. document new --type writer → cria arquivo .json de projeto
          2. export render → gera PDF via LibreOffice headless

        Args:
            content: texto do post (markdown, plaintext ou HTML simples)
            filename: nome do arquivo PDF de saída (sem ou com .pdf)
            output_dir: diretório de saída (default: data/blog_exports/)
            overwrite: sobrescrever se existir

        Returns:
            Path do PDF gerado, ou None se falhou.
        """
        if not self._adapter.is_available("libreoffice"):
            logger.warning("BlogCLIExporter.post_to_pdf: harness libreoffice não disponível")
            return None

        out_dir = output_dir or EXPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        # Garantir extensão .pdf
        pdf_name = filename if filename.endswith(".pdf") else f"{filename}.pdf"
        pdf_path = out_dir / pdf_name
        project_path = out_dir / pdf_name.replace(".pdf", "_project.json")

        # Não sobrescrever se não permitido
        if pdf_path.exists() and not overwrite:
            logger.info(f"BlogCLIExporter: PDF já existe, skip: {pdf_path}")
            return pdf_path

        # Salvar conteúdo em arquivo temporário para referência
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            content_tmp = tmp.name

        try:
            # Fase 1: Criar projeto writer
            r1 = await self._adapter.run(
                "libreoffice",
                ["document", "new", "--type", "writer", "-o", str(project_path)],
                timeout=60,
            )
            if not r1.success:
                logger.error(
                    f"BlogCLIExporter: falha ao criar projeto writer: "
                    f"exit={r1.exit_code} stderr={r1.raw_stderr[:300]}"
                )
                return None

            logger.debug(f"BlogCLIExporter: projeto criado: {project_path}")

            # Fase 2: Export para PDF
            # Sintaxe verificada: cli-anything-libreoffice --project X export render Y.pdf -p pdf
            export_args = [
                "--project", str(project_path),
                "export", "render",
                str(pdf_path),
                "-p", "pdf",  # preset pdf
            ]
            if overwrite:
                export_args.append("--overwrite")

            r2 = await self._adapter.run(
                "libreoffice",
                export_args,
                timeout=120,  # LibreOffice headless pode ser lento
            )

            if r2.success and pdf_path.exists():
                size = pdf_path.stat().st_size
                logger.info(
                    f"BlogCLIExporter: PDF gerado: {pdf_path} ({size} bytes)"
                )
                return pdf_path
            else:
                logger.warning(
                    f"BlogCLIExporter: PDF falhou (exit={r2.exit_code}), "
                    f"tentando ODT como fallback. stderr: {r2.raw_stderr[:200]}"
                )
                return await self._export_odt_fallback(project_path, out_dir, filename)

        except Exception as exc:
            logger.error(f"BlogCLIExporter.post_to_pdf: erro inesperado: {exc}", exc_info=True)
            return None
        finally:
            try:
                os.unlink(content_tmp)
            except OSError:
                pass

    async def _export_odt_fallback(
        self, project_path: Path, out_dir: Path, base_name: str
    ) -> Optional[Path]:
        """Fallback: exportar como ODT se PDF falhar."""
        odt_name = base_name.replace(".pdf", "").replace(".odt", "") + ".odt"
        odt_path = out_dir / odt_name
        r = await self._adapter.run(
            "libreoffice",
            ["export", "render",
             "--project", str(project_path),
             "--output", str(odt_path),
             "--format", "odt",
             "--overwrite"],
            timeout=120,
        )
        if r.success and odt_path.exists():
            logger.info(f"BlogCLIExporter: ODT gerado como fallback: {odt_path}")
            return odt_path
        logger.error(f"BlogCLIExporter: ODT fallback também falhou: {r.raw_stderr[:200]}")
        return None

    async def mermaid_to_image(
        self,
        mermaid_code: str,
        filename: str,
        format: Literal["svg", "png"] = "svg",
        output_dir: Optional[Path] = None,
        overwrite: bool = True,
    ) -> Optional[Path]:
        """
        Renderiza código Mermaid para SVG ou PNG via cli-anything-mermaid.

        Pipeline confirmado na Fase 2:
          1. project new → cria sessão mermaid
          2. diagram set → define o diagrama
          3. export render -f svg|png → renderiza

        Args:
            mermaid_code: código Mermaid (ex: "graph TD\n    A-->B")
            filename: nome base do arquivo (sem extensão)
            format: "svg" (default, mais leve) ou "png"
            output_dir: diretório de saída (default: data/blog_exports/)
            overwrite: sobrescrever se existir

        Returns:
            Path do arquivo gerado, ou None se falhou.
        """
        if not self._adapter.is_available("mermaid"):
            logger.warning("BlogCLIExporter.mermaid_to_image: harness mermaid não disponível")
            return None

        out_dir = output_dir or EXPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        ext = format.lower()
        out_name = f"{filename}.{ext}"
        out_path = out_dir / out_name
        project_path = out_dir / f"{filename}_mermaid_project.json"

        if out_path.exists() and not overwrite:
            logger.info(f"BlogCLIExporter: imagem já existe, skip: {out_path}")
            return out_path

        # Salvar código mermaid em arquivo .mmd
        mmd_path = out_dir / f"{filename}.mmd"
        mmd_path.write_text(mermaid_code, encoding="utf-8")

        try:
            # Fase 1: Criar projeto mermaid
            r1 = await self._adapter.run(
                "mermaid",
                ["project", "new", "-o", str(project_path)],
                timeout=30,
            )

            if r1.success:
                # Fase 2: definir diagrama (sintaxe: --project X diagram set --text "...")
                diagram_text = mmd_path.read_text(encoding="utf-8")
                r2 = await self._adapter.run(
                    "mermaid",
                    ["--project", str(project_path), "diagram", "set", "--text", diagram_text],
                    timeout=30,
                )
                if not r2.success:
                    logger.debug(
                        f"BlogCLIExporter: diagram set falhou, tentando export direto: {r2.raw_stderr[:100]}"
                    )

                # Fase 3: Export render (sintaxe: --project X export render Y.svg -f svg)
                export_args = [
                    "--project", str(project_path),
                    "export", "render",
                    str(out_path),
                    "-f", format,
                ]
                if overwrite:
                    export_args.append("--overwrite")

                r3 = await self._adapter.run("mermaid", export_args, timeout=60)

                if r3.success and out_path.exists():
                    size = out_path.stat().st_size
                    logger.info(
                        f"BlogCLIExporter: {format.upper()} gerado: "
                        f"{out_path} ({size} bytes)"
                    )
                    return out_path

            # Fallback: tentar carregar o .mmd como projeto e exportar
            logger.debug("BlogCLIExporter: tentando export direto do .mmd")
            r_direct = await self._adapter.run(
                "mermaid",
                ["--project", str(mmd_path), "export", "render", str(out_path), "-f", format, "--overwrite"],
                timeout=60,
            )

            if r_direct.success and out_path.exists():
                size = out_path.stat().st_size
                logger.info(
                    f"BlogCLIExporter: {format.upper()} (direto) gerado: "
                    f"{out_path} ({size} bytes)"
                )
                return out_path

            logger.error(
                f"BlogCLIExporter: mermaid render falhou. "
                f"exit={r_direct.exit_code} stderr={r_direct.raw_stderr[:300]}"
            )
            return None

        except Exception as exc:
            logger.error(
                f"BlogCLIExporter.mermaid_to_image: erro inesperado: {exc}",
                exc_info=True
            )
            return None

    async def generate_post_assets(
        self,
        post_id: str,
        content: str,
        diagrams: Optional[list[dict]] = None,
        formats: Optional[list[str]] = None,
    ) -> dict:
        """
        Gera todos os assets de um post em uma única chamada.

        Args:
            post_id: identificador único do post
            content: conteúdo completo do post
            diagrams: lista de dicts com {"name": str, "code": str, "format": "svg"|"png"}
            formats: formatos de documento a gerar (ex: ["pdf", "odt"])

        Returns:
            dict com paths reais de todos os assets gerados
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        result: dict = {
            "post_id": post_id,
            "generated_at": datetime.now().isoformat(),
            "pdf": None,
            "diagrams": [],
        }

        wanted_formats = formats or (["pdf"] if self._adapter.is_available("libreoffice") else [])

        # Gerar PDF se solicitado
        if "pdf" in wanted_formats:
            pdf_path = await self.post_to_pdf(
                content=content,
                filename=f"{post_id}_{ts}",
            )
            result["pdf"] = str(pdf_path) if pdf_path else None

        # Gerar diagramas
        for diagram in (diagrams or []):
            name = diagram.get("name", f"diagram_{ts}")
            code = diagram.get("code", "")
            fmt = diagram.get("format", "svg")
            if not code:
                continue
            img_path = await self.mermaid_to_image(
                mermaid_code=code,
                filename=f"{post_id}_{name}",
                format=fmt,
            )
            result["diagrams"].append({
                "name": name,
                "path": str(img_path) if img_path else None,
                "format": fmt,
                "success": img_path is not None,
            })

        return result
