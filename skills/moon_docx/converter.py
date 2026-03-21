"""DOCX creation and conversion using LibreOffice CLI harness."""
import asyncio
from pathlib import Path
from core.agent_base import TaskResult


class MoonDocxConverter:
    """Create and convert Word documents via LibreOffice."""

    LIBREOFFICE_CMD = "libreoffice"
    SUPPORTED_INPUTS = {".odt", ".pdf", ".html", ".txt", ".rtf"}

    async def convert_to_docx(self, source_path: str, output_dir: str = None, **kwargs) -> TaskResult:
        start = asyncio.get_event_loop().time()
        try:
            src = Path(source_path)
            if not src.exists():
                return TaskResult(success=False, error=f"Arquivo não encontrado: {source_path}")

            out_dir = output_dir or str(src.parent)
            cmd = [self.LIBREOFFICE_CMD, "--headless", "--convert-to", "docx",
                   "--outdir", out_dir, str(src)]

            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode != 0:
                return TaskResult(success=False,
                                  error=f"LibreOffice erro: {stderr.decode().strip()}",
                                  execution_time=asyncio.get_event_loop().time() - start)

            docx_path = Path(out_dir) / (src.stem + ".docx")
            if not docx_path.exists():
                return TaskResult(success=False, error=f"DOCX não gerado em: {docx_path}")

            return TaskResult(
                success=True,
                data={"docx_path": str(docx_path), "source": str(src),
                      "size_bytes": docx_path.stat().st_size},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except asyncio.TimeoutError:
            return TaskResult(success=False, error="Timeout na conversão DOCX (>60s)")
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def html_to_docx(self, html_content: str, output_path: str, **kwargs) -> TaskResult:
        """Converte string HTML para DOCX via arquivo temporário."""
        start = asyncio.get_event_loop().time()
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                             delete=False, encoding='utf-8') as tmp:
                tmp.write(html_content)
                tmp_path = tmp.name

            result = await self.convert_to_docx(tmp_path,
                                                  output_dir=str(Path(output_path).parent))
            Path(tmp_path).unlink(missing_ok=True)

            if result.success:
                generated = result.data.get("docx_path", "")
                if generated != output_path:
                    Path(generated).rename(output_path)
                return TaskResult(success=True,
                                  data={"docx_path": output_path},
                                  execution_time=asyncio.get_event_loop().time() - start)
            return result
        except Exception as e:
            return TaskResult(success=False, error=str(e))