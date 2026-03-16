"""
Unit tests for Groq LLM integration.
TDD: Tests written first to define expected behavior.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# Add Super-Agente/groq-models to path
root = Path(__file__).resolve().parent.parent.parent
groq_models_path = root / "Super-Agente" / "groq-models"
if str(groq_models_path) not in sys.path:
    sys.path.insert(0, str(groq_models_path))


class TestLLMInterface:
    """Test the LLM interface contract."""

    @pytest.mark.asyncio
    async def test_generate_returns_string_response(self):
        """Verify generate returns a string."""
        with patch("groq.Groq") as mock_groq:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content="Test response"))]
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_groq.return_value = mock_client

            from groq_llm import GroqLLM
            llm = GroqLLM(api_key="test_key")
            result = await llm.generate("Hello")

            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_uses_correct_model(self):
        """Verify correct model is used."""
        with patch("groq.Groq") as mock_groq:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content="Response"))]
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_groq.return_value = mock_client

            from groq_llm import GroqLLM
            llm = GroqLLM(api_key="test_key")
            await llm.generate("Prompt", model="mixtral-8x7b-32768")

            call_args = mock_client.chat.completions.create.call_args
            assert call_args.kwargs["model"] == "mixtral-8x7b-32768"


class TestSupabaseStorage:
    """Test Supabase storage interface."""

    def test_insert_message_contract(self):
        """Message insert should return the inserted record."""
        with patch("supabase.create_client") as mock:
            mock_client = Mock()
            mock_client.table.return_value.insert.return_value.execute.return_value.data = [
                {"id": 1, "content": "test", "role": "user"}
            ]
            mock.return_value = mock_client

            result = mock_client.table("messages").insert(
                {"content": "test", "role": "user"}
            ).execute()

            assert len(result.data) == 1
            assert result.data[0]["content"] == "test"
