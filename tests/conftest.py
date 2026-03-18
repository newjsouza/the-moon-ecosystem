def binary_works(name: str, test_args: list = ["--help"]) -> bool:
    """Verifica se um binário está disponível e funciona corretamente."""
    if not shutil.which(name):
        return False
    try:
        result = subprocess.run([name] + test_args, capture_output=True, timeout=10)
        # Consideramos que funciona se não teve timeout e retornou 0 ou 1 (ajuda exibida)
        return result.returncode in [0, 1]
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


"""
tests/conftest.py
Pytest configuration, fixtures and markers for The Moon Ecosystem.
"""
import pytest
import sys
import os
import asyncio
import shutil  # Adicionado para verificação de binários
import subprocess
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

def binary_available(name: str) -> bool:
    """Verifica se um binário está disponível no PATH."""
    return shutil.which(name) is not None


def binary_works(name: str, test_args: list = ["--help"]) -> bool:
    """Verifica se um binário está disponível e funciona corretamente."""
    import subprocess
    if not binary_available(name):
        return False
    try:
        result = subprocess.run([name] + test_args, capture_output=True, timeout=10)
        # Consideramos que funciona se não teve timeout e retornou 0 ou 1 (ajuda exibida)
        # Mas vamos verificar mais cuidadosamente se não tem erros críticos
        stderr_output = result.stderr.decode() if result.stderr else ""
        
        # Verificar se tem erros críticos como PackageNotFoundError
        if "PackageNotFoundError" in stderr_output or "importlib.metadata" in stderr_output:
            return False
            
        # Caso contrário, assumimos que se não teve timeout, está OK
        return result.returncode in [0, 1]
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def pytest_configure(config):
    """Register custom pytest markers."""
    # Test categories
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (external services)")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    
    # Provider-specific markers (require API keys)
    config.addinivalue_line("markers", "requires_groq: Tests requiring GROQ_API_KEY")
    config.addinivalue_line("markers", "requires_telegram: Tests requiring TELEGRAM_BOT_TOKEN")
    config.addinivalue_line("markers", "requires_github: Tests requiring GITHUB_TOKEN")
    config.addinivalue_line("markers", "requires_gemini: Tests requiring GEMINI_API_KEY")
    config.addinivalue_line("markers", "requires_openrouter: Tests requiring OPENROUTER_API_KEY")
    config.addinivalue_line("markers", "requires_alpha_vantage: Tests requiring ALPHA_VANTAGE_API_KEY")
    
    # Agent-specific markers
    config.addinivalue_line("markers", "watchdog: WatchdogAgent tests")
    config.addinivalue_line("markers", "economic_sentinel: EconomicSentinel tests")
    config.addinivalue_line("markers", "omni_channel: OmniChannelStrategist tests")
    config.addinivalue_line("markers", "architect: ArchitectAgent tests")
    config.addinivalue_line("markers", "llm_router: LLMRouter tests")


# Marks reutilizáveis para testes que dependem de binários externos
requires_libreoffice = pytest.mark.skipif(
    not binary_works("cli-anything-libreoffice"),
    reason="cli-anything-libreoffice falha ao executar --help — teste de integração real"
)

requires_mermaid = pytest.mark.skipif(
    not binary_works("cli-anything-mermaid"),
    reason="cli-anything-mermaid falha ao executar --help — teste de integração real"
)

requires_obs = pytest.mark.skipif(
    not binary_works("cli-anything-obs-studio"),
    reason="cli-anything-obs-studio falha ao executar — teste de integração real"
)


# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_groq_client():
    """Mock Groq client for testing."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Mocked Groq response"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_message_bus():
    """Mock MessageBus for testing."""
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=None)
    bus.subscribe = MagicMock(return_value=None)
    return bus


@pytest.fixture
def env_cleanup():
    """
    Fixture to cleanup environment variables after test.

    Also clears LLM-related env vars before test to ensure isolation
    from .env file values.
    """
    # Clear LLM-related env vars BEFORE test
    for key in ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"]:
        os.environ[key] = ""

    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def skip_if_no_groq():
    """Skip test if GROQ_API_KEY is not configured."""
    if not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") in ["", "COLE_O_SEU_TOKEN_AQUI"]:
        pytest.skip("GROQ_API_KEY not configured")


def skip_if_no_telegram():
    """Skip test if TELEGRAM_BOT_TOKEN is not configured."""
    if not os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") == "":
        pytest.skip("TELEGRAM_BOT_TOKEN not configured")


def skip_if_no_github():
    """Skip test if GITHUB_TOKEN is not configured."""
    if not os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") == "":
        pytest.skip("GITHUB_TOKEN not configured")
