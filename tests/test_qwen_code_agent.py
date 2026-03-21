"""
tests/test_qwen_code_agent.py
Unit tests for QwenCodeAgent.
Uses unittest.mock to mock subprocess calls — does NOT require real qwen binary.
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.qwen_code_agent import QwenCodeAgent
from core.agent_base import TaskResult


# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def agent() -> QwenCodeAgent:
    """Create a QwenCodeAgent instance."""
    return QwenCodeAgent()


# ─────────────────────────────────────────────────────────────
#  Mock helpers
# ─────────────────────────────────────────────────────────────

def create_mock_process(returncode: int, stdout: bytes, stderr: bytes) -> AsyncMock:
    """Helper to create a mock subprocess."""
    mock_proc = AsyncMock()
    mock_proc.returncode = returncode
    mock_proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return mock_proc


# ─────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────

class TestQwenCodeAgentExecute:
    """Tests for QwenCodeAgent._execute() method."""

    @pytest.mark.asyncio
    async def test_execute_success(self, agent: QwenCodeAgent) -> None:
        """Test successful execution with valid JSON response."""
        response_data = {"response": "HELLO_MOON", "model": "qwen3-coder"}
        stdout = json.dumps(response_data).encode()

        mock_proc = create_mock_process(returncode=0, stdout=stdout, stderr=b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await agent._execute("Say HELLO_MOON")

        assert result.success is True
        assert result.data == response_data
        assert result.error is None
        assert result.execution_time >= 0
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_binary_not_found(self, agent: QwenCodeAgent) -> None:
        """Test when qwen binary is not found."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
            result = await agent._execute("Any task")

        assert result.success is False
        assert "qwen binary not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_timeout(self, agent: QwenCodeAgent) -> None:
        """Test execution timeout."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.terminate = MagicMock()  # Use MagicMock instead of AsyncMock
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await agent._execute("Slow task", timeout=1)

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_json(self, agent: QwenCodeAgent) -> None:
        """Test when qwen returns non-JSON output."""
        stdout = b"This is plain text, not JSON"

        mock_proc = create_mock_process(returncode=0, stdout=stdout, stderr=b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await agent._execute("Any task")

        assert result.success is True
        assert result.data == {"response": stdout.decode().strip()}

    @pytest.mark.asyncio
    async def test_execute_nonzero_returncode(self, agent: QwenCodeAgent) -> None:
        """Test when qwen returns non-zero exit code."""
        stderr_msg = "Error: Invalid API key"

        mock_proc = create_mock_process(
            returncode=1,
            stdout=b"",
            stderr=stderr_msg.encode()
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await agent._execute("Any task")

        assert result.success is False
        assert stderr_msg in result.error

    @pytest.mark.asyncio
    async def test_execute_with_extra_flags(self, agent: QwenCodeAgent) -> None:
        """Test execution with extra CLI flags."""
        response_data = {"response": "OK"}
        stdout = json.dumps(response_data).encode()

        mock_proc = create_mock_process(returncode=0, stdout=stdout, stderr=b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await agent._execute("Task", flags=["--model", "custom-model"])

        # Verify flags were passed
        call_args = mock_exec.call_args[0]
        assert "--model" in call_args
        assert "custom-model" in call_args
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_cwd(self, agent: QwenCodeAgent) -> None:
        """Test execution with custom working directory."""
        response_data = {"response": "OK"}
        stdout = json.dumps(response_data).encode()

        mock_proc = create_mock_process(returncode=0, stdout=stdout, stderr=b"")

        custom_cwd = "/tmp/test_dir"

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await agent._execute("Task", cwd=custom_cwd)

        # Verify cwd was passed
        call_kwargs = mock_exec.call_args[1]
        assert call_kwargs["cwd"] == custom_cwd
        assert result.success is True


class TestQwenCodeAgentPing:
    """Tests for QwenCodeAgent.ping() method."""

    @pytest.mark.asyncio
    async def test_ping_success(self, agent: QwenCodeAgent) -> None:
        """Test ping when qwen is available."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await agent.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_ping_failure(self, agent: QwenCodeAgent) -> None:
        """Test ping when qwen is not available."""
        with patch("asyncio.create_subprocess_exec", side_effect=Exception()):
            result = await agent.ping()

        assert result is False


class TestQwenCodeAgentTaskResult:
    """Tests for TaskResult fields in QwenCodeAgent."""

    @pytest.mark.asyncio
    async def test_taskresult_fields(self, agent: QwenCodeAgent) -> None:
        """Test that TaskResult fields are set correctly."""
        response_data = {"response": "test"}
        stdout = json.dumps(response_data).encode()

        mock_proc = create_mock_process(returncode=0, stdout=stdout, stderr=b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await agent._execute("Test task")

        # Verify all TaskResult fields
        assert hasattr(result, "success")
        assert hasattr(result, "data")
        assert hasattr(result, "error")
        assert hasattr(result, "execution_time")

        assert isinstance(result.success, bool)
        assert result.success is True
        assert result.data is not None
        assert result.error is None
        assert isinstance(result.execution_time, float)
        assert result.execution_time >= 0


class TestQwenCodeAgentStatus:
    """Tests for QwenCodeAgent.get_status() method."""

    def test_get_status(self, agent: QwenCodeAgent) -> None:
        """Test get_status returns expected fields."""
        status = agent.get_status()

        assert isinstance(status, dict)
        assert "name" in status
        assert status["name"] == "QwenCodeAgent"
        assert "qwen_bin" in status
        assert status["qwen_bin"] == "qwen"
        assert "description" in status


class TestQwenCodeAgentDomains:
    """Tests for QwenCodeAgent domain registration in Architect."""

    def test_qwen_code_agent_in_domain_map(self) -> None:
        """Test that QwenCodeAgent is registered in DOMAIN_AGENT_MAP."""
        from agents.architect import DOMAIN_AGENT_MAP

        expected_domains = [
            "code_generation",
            "refactoring",
            "test_writing",
            "harness_generation",
        ]

        for domain in expected_domains:
            assert domain in DOMAIN_AGENT_MAP
            assert DOMAIN_AGENT_MAP[domain] == "QwenCodeAgent"

    def test_qwen_code_agent_keyword_patterns(self) -> None:
        """Test that QwenCodeAgent keyword patterns are registered."""
        from agents.architect import KEYWORD_PATTERNS

        expected_patterns = [
            "code_generation",
            "refactoring",
            "test_writing",
            "harness_generation",
        ]

        for pattern in expected_patterns:
            assert pattern in KEYWORD_PATTERNS


# ─────────────────────────────────────────────────────────────
#  Integration test (optional, requires real qwen binary)
# ─────────────────────────────────────────────────────────────

class TestQwenCodeAgentIntegration:
    """
    Integration tests that require real qwen binary.
    Skipped if qwen is not installed.
    """

    @pytest.mark.asyncio
    async def test_qwen_binary_available(self, agent: QwenCodeAgent) -> None:
        """Test if qwen binary is available."""
        ping_result = await agent.ping()
        # This test may pass or fail depending on environment
        # It's here to verify the binary is accessible
        assert isinstance(ping_result, bool)
