"""
tests/test_llm_fallback.py
Testes de fallback em cascata do LLMRouter.

Cenários testados:
  - Apenas Groq configurado
  - Groq indisponível → modo degradado
  - Chave inválida
  - Rate limit simulado
  - Model pool fallback
"""
import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock

from agents.llm import (
    LLMRouter,
    GroqProvider,
    RateLimitError,
    ServiceUnavailableError,
)


# ─────────────────────────────────────────────────────────────
#  Testes de Fallback Groq → Modo Degradado
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_fallback_groq_to_degraded(env_cleanup):
    """Testa fallback de Groq para modo degradado quando Groq falha."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    # Mock Groq para falhar
    mock_groq_client = AsyncMock()
    mock_groq_client.chat.completions.create.side_effect = ServiceUnavailableError("Groq down")

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("test prompt")

        # Deve ter fallback para modo degradado
        assert result is not None
        assert "MODO DEGRADADO" in result or "indisponíveis" in result
        assert router.usage_stats["degraded"] > 0


@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_fallback_groq_rate_limit_to_degraded(env_cleanup):
    """Testa fallback de Groq para modo degradado por rate limit."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    # Mock Groq para rate limit
    mock_groq_client = AsyncMock()
    mock_groq_client.chat.completions.create.side_effect = Exception("429 Too Many Requests")

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("test prompt")

        # Deve fallback para modo degradado
        assert result is not None
        assert "MODO DEGRADADO" in result or "indisponíveis" in result


# ─────────────────────────────────────────────────────────────
#  Testes de Modo Degradado
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_degraded_mode_no_providers(env_cleanup):
    """Testa modo degradado quando nenhum provider está configurado."""
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    router = LLMRouter()
    result = await router.complete("Olá, preciso de ajuda")

    # Deve retornar resposta degradada
    assert result is not None
    assert "MODO DEGRADADO" in result or "indisponíveis" in result
    # Nota: usage_stats["degraded"] pode ser 0 se nenhum provider foi tentado


@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_degraded_mode_all_providers_fail(env_cleanup):
    """Testa modo degradado quando todos providers falham."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    # Mock Groq para falhar
    mock_groq_client = AsyncMock()
    mock_groq_client.chat.completions.create.side_effect = ServiceUnavailableError("All down")

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("test prompt")

        # Deve cair em modo degradado
        assert result is not None
        assert "MODO DEGRADADO" in result or "indisponíveis" in result
        assert router.usage_stats["degraded"] > 0


# ─────────────────────────────────────────────────────────────
#  Testes de Chave Inválida
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_invalid_groq_key(env_cleanup):
    """Testa comportamento com chave inválida do Groq."""
    os.environ["GROQ_API_KEY"] = "invalid_key_123"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    # Mock Groq para falhar com autenticação inválida
    mock_groq_client = AsyncMock()
    mock_groq_client.chat.completions.create.side_effect = Exception("401 Unauthorized")

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("test prompt")

        # Deve fallback para modo degradado
        assert result is not None
        assert "MODO DEGRADADO" in result or "indisponíveis" in result


# ─────────────────────────────────────────────────────────────
#  Testes de Rate Limit
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_rate_limit_recovery(env_cleanup):
    """Testa recuperação após rate limit."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    # Mock Groq: primeira chamada rate limit, segunda sucesso
    mock_groq_client = AsyncMock()

    success_response = MagicMock()
    success_response.choices = [MagicMock()]
    success_response.choices[0].message.content = "Success after rate limit"

    mock_groq_client.chat.completions.create.side_effect = [
        Exception("429 Too Many Requests"),
        success_response,
    ]

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()

        # Primeira chamada: rate limit → fallback para degraded
        result1 = await router.complete("test prompt 1")

        # Segunda chamada: deve ter sucesso com Groq (model pool)
        result2 = await router.complete("test prompt 2")

        # Segunda chamada deve ter sucesso
        assert "Success after rate limit" in result2 or result2 != result1


# ─────────────────────────────────────────────────────────────
#  Testes de Model Pool (Fallback interno do Groq)
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_groq_model_pool_fallback(env_cleanup):
    """Testa fallback entre modelos dentro do pool do Groq."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    mock_groq_client = AsyncMock()

    # Primeiro modelo falha, segundo tem sucesso
    success_response = MagicMock()
    success_response.choices = [MagicMock()]
    success_response.choices[0].message.content = "Success with second model"

    mock_groq_client.chat.completions.create.side_effect = [
        Exception("Model overloaded"),
        success_response,
    ]

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("test prompt", task_type="complex")

        assert "Success with second model" in result


# ─────────────────────────────────────────────────────────────
#  Testes de Task Type
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_task_type_complex(env_cleanup):
    """Testa task type complex (usa llama-3.3-70b)."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    mock_groq_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Complex task response"
    mock_groq_client.chat.completions.create.return_value = mock_response

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("Analyze this complex problem", task_type="complex")

        assert "Complex task response" in result


@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_task_type_fast(env_cleanup):
    """Testa task type fast (usa llama-3.1-8b)."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    mock_groq_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Fast response"
    mock_groq_client.chat.completions.create.return_value = mock_response

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("Quick question", task_type="fast")

        assert "Fast response" in result


@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_task_type_coding(env_cleanup):
    """Testa task type coding."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    mock_groq_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "def hello(): pass"
    mock_groq_client.chat.completions.create.return_value = mock_response

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()
        result = await router.complete("Write a function", task_type="coding")

        assert "def hello(): pass" in result


# ─────────────────────────────────────────────────────────────
#  Testes de Usage Stats
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_usage_stats_tracking(env_cleanup):
    """Testa que usage stats são rastreados corretamente."""
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""

    mock_groq_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Response"
    mock_groq_client.chat.completions.create.return_value = mock_response

    with patch('groq.AsyncGroq', return_value=mock_groq_client):
        router = LLMRouter()

        # Executa múltiplas chamadas
        await router.complete("prompt 1")
        await router.complete("prompt 2")
        await router.complete("prompt 3")

        stats = router.get_usage_stats()

        assert stats["groq"] == 3
        assert stats["degraded"] == 0


# ─────────────────────────────────────────────────────────────
#  Testes de GroqProvider Direto
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_groq_provider_rate_limit_fallback():
    """Testa fallback quando Groq atinge rate limit."""
    provider = GroqProvider(api_key="test_key")

    # Mock do cliente Groq para simular rate limit
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("429 Too Many Requests")

    with patch.object(provider, '_client', mock_client):
        with pytest.raises((RateLimitError, ServiceUnavailableError)):
            await provider.complete("test prompt")


@pytest.mark.unit
@pytest.mark.llm_router
@pytest.mark.asyncio
async def test_groq_provider_service_unavailable():
    """Testa erro de serviço indisponível."""
    provider = GroqProvider(api_key="test_key")

    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = ServiceUnavailableError("Service down")

    with patch.object(provider, '_client', mock_client):
        with pytest.raises(ServiceUnavailableError):
            await provider.complete("test prompt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
