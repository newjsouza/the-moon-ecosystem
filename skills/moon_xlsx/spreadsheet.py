"""XLSX creation using LibreOffice and openpyxl."""
import asyncio
from pathlib import Path
from core.agent_base import TaskResult


class MoonXLSXSpreadsheet:
    """Create and manipulate Excel spreadsheets."""

    LIBREOFFICE_CMD = "libreoffice"

    async def create_from_data(self, data: list[dict], output_path: str,
                                sheet_name: str = "Sheet1", **kwargs) -> TaskResult:
        """Cria XLSX a partir de lista de dicts. Cada dict = uma linha."""
        start = asyncio.get_event_loop().time()
        try:
            import importlib.util
            if importlib.util.find_spec("openpyxl") is None:
                return TaskResult(success=False,
                                  error="openpyxl não instalado: pip install openpyxl")

            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet_name

            if not data:
                return TaskResult(success=False, error="data está vazia")

            headers = list(data[0].keys())
            ws.append(headers)
            for row in data:
                ws.append([row.get(h, "") for h in headers])

            wb.save(output_path)
            path = Path(output_path)

            return TaskResult(
                success=True,
                data={"xlsx_path": output_path, "rows": len(data),
                      "columns": len(headers), "size_bytes": path.stat().st_size},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def convert_to_xlsx(self, source_path: str,
                               output_dir: str = None, **kwargs) -> TaskResult:
        """Converte ODS/CSV/outros para XLSX via LibreOffice."""
        start = asyncio.get_event_loop().time()
        try:
            src = Path(source_path)
            if not src.exists():
                return TaskResult(success=False, error=f"Arquivo não encontrado: {source_path}")

            out_dir = output_dir or str(src.parent)
            cmd = [self.LIBREOFFICE_CMD, "--headless", "--convert-to", "xlsx",
                   "--outdir", out_dir, str(src)]

            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode != 0:
                return TaskResult(success=False,
                                  error=f"LibreOffice erro: {stderr.decode().strip()}")

            xlsx_path = Path(out_dir) / (src.stem + ".xlsx")
            return TaskResult(
                success=True,
                data={"xlsx_path": str(xlsx_path)},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))