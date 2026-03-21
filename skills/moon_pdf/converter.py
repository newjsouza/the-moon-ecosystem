"""PDF conversion using LibreOffice CLI harness."""
import os
import asyncio
import subprocess
from pathlib import Path
from core.agent_base import TaskResult


class MoonPDFConverter:
    """Convert documents to PDF and manipulate PDFs via LibreOffice."""

    LIBREOFFICE_CMD = "libreoffice"
    SUPPORTED_INPUTS = {".docx", ".doc", ".odt", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".txt"}

    async def convert_to_pdf(self, source_path: str, output_dir: str = None, **kwargs) -> TaskResult:
        start = asyncio.get_event_loop().time()
        try:
            src = Path(source_path)
            if not src.exists():
                return TaskResult(success=False, error=f"Arquivo não encontrado: {source_path}")
            if src.suffix.lower() not in self.SUPPORTED_INPUTS:
                return TaskResult(success=False, error=f"Formato não suportado: {src.suffix}")

            out_dir = output_dir or str(src.parent)
            cmd = [self.LIBREOFFICE_CMD, "--headless", "--convert-to", "pdf",
                   "--outdir", out_dir, str(src)]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode != 0:
                return TaskResult(
                    success=False,
                    error=f"LibreOffice erro: {stderr.decode().strip()}",
                    execution_time=asyncio.get_event_loop().time() - start
                )

            pdf_path = Path(out_dir) / (src.stem + ".pdf")
            if not pdf_path.exists():
                return TaskResult(success=False, error=f"PDF não gerado em: {pdf_path}")

            return TaskResult(
                success=True,
                data={"pdf_path": str(pdf_path), "source": str(src), "size_bytes": pdf_path.stat().st_size},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except asyncio.TimeoutError:
            return TaskResult(success=False, error="Timeout na conversão PDF (>60s)")
        except Exception as e:
            return TaskResult(success=False, error=str(e),
                              execution_time=asyncio.get_event_loop().time() - start)

    async def merge_pdfs(self, pdf_paths: list, output_path: str, **kwargs) -> TaskResult:
        start = asyncio.get_event_loop().time()
        try:
            for p in pdf_paths:
                if not Path(p).exists():
                    return TaskResult(success=False, error=f"PDF não encontrado: {p}")

            import importlib.util
            if importlib.util.find_spec("pypdf") is None:
                return TaskResult(success=False, error="pypdf não instalado: pip install pypdf")

            from pypdf import PdfWriter
            writer = PdfWriter()
            for pdf_path in pdf_paths:
                from pypdf import PdfReader
                reader = PdfReader(pdf_path)
                for page in reader.pages:
                    writer.add_page(page)

            with open(output_path, "wb") as f:
                writer.write(f)

            return TaskResult(
                success=True,
                data={"output_path": output_path, "merged_count": len(pdf_paths)},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))