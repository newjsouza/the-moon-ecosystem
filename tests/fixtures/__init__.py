import os
import pytest
from unittest.mock import Mock, patch

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_ANON_KEY", "test_anon_key")
os.environ.setdefault("GROQ_API_KEY", "test_groq_key")
os.environ.setdefault("OPENAI_API_KEY", "test_openai_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_anthropic_key")


@pytest.fixture
def mock_supabase():
    with patch("supabase.create_client") as mock:
        client = Mock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_groq():
    with patch("groq.Groq") as mock:
        client = Mock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_openai():
    with patch("openai.OpenAI") as mock:
        client = Mock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_anthropic():
    with patch("anthropic.Anthropic") as mock:
        client = Mock()
        mock.return_value = client
        yield client
