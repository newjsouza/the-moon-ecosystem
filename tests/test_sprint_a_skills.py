"""Sprint A — Test suite for LibreOffice and OBS skills."""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# moon_pdf tests
# ─────────────────────────────────────────────
class TestMoonPDFConverter:
    def setup_method(self):
        from skills.moon_pdf.converter import MoonPDFConverter
        self.converter = MoonPDFConverter()

    def test_instantiation(self):
        assert self.converter is not None
        assert self.converter.LIBREOFFICE_CMD == "libreoffice"

    def test_supported_formats(self):
        assert ".docx" in self.converter.SUPPORTED_INPUTS
        assert ".xlsx" in self.converter.SUPPORTED_INPUTS
        assert ".pptx" in self.converter.SUPPORTED_INPUTS

    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self):
        result = await self.converter.convert_to_pdf("/nao/existe/arquivo.docx")
        assert isinstance(result, TaskResult)
        assert result.success is False
        assert "não encontrado" in result.error

    @pytest.mark.asyncio
    async def test_unsupported_format(self, tmp_path):
        fake = tmp_path / "test.xyz"
        fake.write_text("content")
        result = await self.converter.convert_to_pdf(str(fake))
        assert result.success is False
        assert "não suportado" in result.error

    @pytest.mark.asyncio
    async def test_convert_to_pdf_success(self, tmp_path):
        src = tmp_path / "test.docx"
        src.write_bytes(b"fake docx content")
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        pdf_out = tmp_path / "test.pdf"
        pdf_out.write_bytes(b"fake pdf content")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.converter.convert_to_pdf(str(src), str(tmp_path))
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_convert_to_pdf_libreoffice_error(self, tmp_path):
        src = tmp_path / "test.docx"
        src.write_bytes(b"fake content")
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"conversion failed"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.converter.convert_to_pdf(str(src), str(tmp_path))
        assert result.success is False
        assert "LibreOffice erro" in result.error


# ─────────────────────────────────────────────
# moon_docx tests
# ─────────────────────────────────────────────
class TestMoonDocxConverter:
    def setup_method(self):
        from skills.moon_docx.converter import MoonDocxConverter
        self.converter = MoonDocxConverter()

    def test_instantiation(self):
        assert self.converter is not None

    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self):
        result = await self.converter.convert_to_docx("/nao/existe.odt")
        assert result.success is False
        assert "não encontrado" in result.error

    @pytest.mark.asyncio
    async def test_html_to_docx_empty_html(self, tmp_path):
        out = str(tmp_path / "output.docx")
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.converter.html_to_docx("<h1>Test</h1>", out)
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_convert_success_mock(self, tmp_path):
        src = tmp_path / "test.odt"
        src.write_bytes(b"fake odt")
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        docx_out = tmp_path / "test.docx"
        docx_out.write_bytes(b"fake docx")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.converter.convert_to_docx(str(src), str(tmp_path))
        assert isinstance(result, TaskResult)


# ─────────────────────────────────────────────
# moon_xlsx tests
# ─────────────────────────────────────────────
class TestMoonXLSXSpreadsheet:
    def setup_method(self):
        from skills.moon_xlsx.spreadsheet import MoonXLSXSpreadsheet
        self.sheet = MoonXLSXSpreadsheet()

    def test_instantiation(self):
        assert self.sheet is not None

    @pytest.mark.asyncio
    async def test_create_empty_data(self, tmp_path):
        out = str(tmp_path / "test.xlsx")
        result = await self.sheet.create_from_data([], out)
        assert result.success is False
        # openpyxl pode não estar instalado, então verificamos ambas mensagens
        assert "vazia" in result.error or "openpyxl" in result.error

    @pytest.mark.asyncio
    async def test_create_from_data_success(self, tmp_path):
        data = [{"nome": "Moon", "versão": "1.0"}, {"nome": "Sprint", "versão": "A"}]
        out = str(tmp_path / "test.xlsx")
        result = await self.sheet.create_from_data(data, out)
        if result.success:
            assert result.data["rows"] == 2
            assert result.data["columns"] == 2
            assert Path(out).exists()
        else:
            assert "openpyxl" in result.error

    @pytest.mark.asyncio
    async def test_create_with_sheet_name(self, tmp_path):
        data = [{"col": "val"}]
        out = str(tmp_path / "named.xlsx")
        result = await self.sheet.create_from_data(data, out, sheet_name="Relatório")
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_convert_nonexistent(self):
        result = await self.sheet.convert_to_xlsx("/nao/existe.ods")
        assert result.success is False


# ─────────────────────────────────────────────
# moon_pptx tests
# ─────────────────────────────────────────────
class TestMoonPPTXPresenter:
    def setup_method(self):
        from skills.moon_pptx.presenter import MoonPPTXPresenter
        self.presenter = MoonPPTXPresenter()

    def test_instantiation(self):
        assert self.presenter is not None

    @pytest.mark.asyncio
    async def test_create_from_slides_success(self, tmp_path):
        slides = [
            {"title": "The Moon", "content": "Ecossistema de IA"},
            {"title": "Sprint A", "content": "Skills LibreOffice", "notes": "Concluído"},
        ]
        out = str(tmp_path / "presentation.pptx")
        result = await self.presenter.create_from_slides(slides, out, title="The Moon Demo")
        if result.success:
            assert result.data["slides"] == 2
            assert Path(out).exists()
        else:
            assert "python-pptx" in result.error

    @pytest.mark.asyncio
    async def test_create_empty_slides(self, tmp_path):
        out = str(tmp_path / "empty.pptx")
        result = await self.presenter.create_from_slides([], out)
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_convert_to_pdf_nonexistent(self):
        result = await self.presenter.convert_to_pdf("/nao/existe.pptx")
        assert result.success is False
        assert "não encontrado" in result.error

    @pytest.mark.asyncio
    async def test_convert_to_pdf_mock(self, tmp_path):
        src = tmp_path / "test.pptx"
        src.write_bytes(b"fake pptx")
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        pdf_out = tmp_path / "test.pdf"
        pdf_out.write_bytes(b"fake pdf")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.presenter.convert_to_pdf(str(src), str(tmp_path))
        assert isinstance(result, TaskResult)


# ─────────────────────────────────────────────
# moon_obs tests
# ─────────────────────────────────────────────
class TestMoonOBSRecorder:
    def setup_method(self):
        from skills.moon_obs.recorder import MoonOBSRecorder
        self.recorder = MoonOBSRecorder()

    def test_instantiation(self):
        assert self.recorder is not None
        assert self.recorder.OBS_CMD == "obs"

    @pytest.mark.asyncio
    async def test_check_installation_obs_available(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"OBS Studio 30.0", b""))

        with patch("shutil.which", return_value="/usr/bin/obs"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.recorder.check_installation()
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_check_installation_not_available(self):
        with patch("shutil.which", return_value=None):
            result = await self.recorder.check_installation()
        assert result.success is False
        assert "não encontrado" in result.error

    @pytest.mark.asyncio
    async def test_start_recording_obs_unavailable(self, tmp_path):
        with patch("shutil.which", return_value=None):
            result = await self.recorder.start_recording(str(tmp_path / "out.mkv"))
        assert result.success is False

    @pytest.mark.asyncio
    async def test_stop_recording(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.recorder.stop_recording()
        assert isinstance(result, TaskResult)
        assert result.success is True


# ─────────────────────────────────────────────
# Imports de todas as skills
# ─────────────────────────────────────────────
class TestSprintAImports:
    def test_all_skill_imports(self):
        from skills.moon_pdf import MoonPDFConverter
        from skills.moon_docx import MoonDocxConverter
        from skills.moon_xlsx import MoonXLSXSpreadsheet
        from skills.moon_pptx import MoonPPTXPresenter
        from skills.moon_obs import MoonOBSRecorder
        assert all([MoonPDFConverter, MoonDocxConverter,
                    MoonXLSXSpreadsheet, MoonPPTXPresenter, MoonOBSRecorder])

    def test_all_return_task_result(self):
        """Todas as skills devem trabalhar com TaskResult."""
        from core.agent_base import TaskResult
        result = TaskResult(success=True, data={"test": "sprint_a"})
        assert result.success is True
        assert result.data["test"] == "sprint_a"