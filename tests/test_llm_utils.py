"""
tests/test_llm_utils.py
Testes para funções utilitárias do LLM Router.

Cobertura:
  - validate_llm_env()
  - get_available_llm_providers()
  - print_llm_status()
  - Cenários com diferentes combinações de API keys
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from io import StringIO


# ─────────────────────────────────────────────────────────────
#  Testes de validate_llm_env()
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
def test_validate_llm_env_no_keys(env_cleanup):
    """Testa validação sem nenhuma API key configurada."""
    from agents.llm import validate_llm_env
    
    # Remove todas as keys
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    status = validate_llm_env()
    
    assert status["configured"]["groq"] is False
    assert status["configured"]["gemini"] is False
    assert status["configured"]["openrouter"] is False
    assert status["providers_configured"] == []
    assert status["fallback_chain"] == ["degraded_mode"]
    assert status["fully_configured"] is False
    assert len(status["recommendations"]) > 0


@pytest.mark.unit
@pytest.mark.llm_router
def test_validate_llm_env_groq_only(env_cleanup):
    """Testa validação com apenas Groq configurado."""
    from agents.llm import validate_llm_env
    
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    status = validate_llm_env()
    
    assert status["configured"]["groq"] is True
    assert status["configured"]["gemini"] is False
    assert status["configured"]["openrouter"] is False
    assert status["providers_configured"] == ["Groq"]
    assert status["fallback_chain"] == ["Groq"]
    assert status["fully_configured"] is True


@pytest.mark.unit
@pytest.mark.llm_router
def test_validate_llm_env_all_providers(env_cleanup):
    """Testa validação com todos providers configurados."""
    from agents.llm import validate_llm_env
    
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = "test_gemini_key"
    os.environ["OPENROUTER_API_KEY"] = "test_openrouter_key"
    
    status = validate_llm_env()
    
    assert status["configured"]["groq"] is True
    assert status["configured"]["gemini"] is True
    assert status["configured"]["openrouter"] is True
    assert len(status["providers_configured"]) == 3
    assert "Groq" in status["providers_configured"]
    assert "Gemini" in status["providers_configured"]
    assert "OpenRouter" in status["providers_configured"]
    assert status["fallback_chain"] == ["Groq", "Gemini", "OpenRouter"]
    assert status["fully_configured"] is True


@pytest.mark.unit
@pytest.mark.llm_router
def test_validate_llm_env_invalid_key(env_cleanup):
    """Testa validação com chave inválida (placeholder)."""
    from agents.llm import validate_llm_env
    
    os.environ["GROQ_API_KEY"] = "COLE_O_SEU_TOKEN_AQUI"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    status = validate_llm_env()
    
    assert status["configured"]["groq"] is False
    assert status["fully_configured"] is False


@pytest.mark.unit
@pytest.mark.llm_router
def test_validate_llm_env_recommendations(env_cleanup):
    """Testa que recomendações são geradas corretamente."""
    from agents.llm import validate_llm_env
    
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    status = validate_llm_env()
    
    recommendations = status["recommendations"]
    
    # Deve ter recomendação para Groq
    assert any("GROQ_API_KEY" in rec for rec in recommendations)
    # Deve ter recomendação para Gemini
    assert any("GEMINI_API_KEY" in rec for rec in recommendations)
    # Deve ter recomendação para OpenRouter
    assert any("OPENROUTER_API_KEY" in rec for rec in recommendations)


# ─────────────────────────────────────────────────────────────
#  Testes de get_available_llm_providers()
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
def test_get_available_llm_providers_none(env_cleanup):
    """Testa obtenção de providers sem nenhum configurado."""
    from agents.llm import get_available_llm_providers
    
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    providers = get_available_llm_providers()
    
    assert providers == []


@pytest.mark.unit
@pytest.mark.llm_router
def test_get_available_llm_providers_all(env_cleanup):
    """Testa obtenção de providers com todos configurados."""
    from agents.llm import get_available_llm_providers
    
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = "test_gemini_key"
    os.environ["OPENROUTER_API_KEY"] = "test_openrouter_key"
    
    providers = get_available_llm_providers()
    
    assert len(providers) == 3
    assert providers == ["Groq", "Gemini", "OpenRouter"]


@pytest.mark.unit
@pytest.mark.llm_router
def test_get_available_llm_providers_order(env_cleanup):
    """Testa que ordem de providers segue hierarquia de fallback."""
    from agents.llm import get_available_llm_providers
    
    # Configura apenas Gemini e OpenRouter (sem Groq)
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = "test_gemini_key"
    os.environ["OPENROUTER_API_KEY"] = "test_openrouter_key"
    
    providers = get_available_llm_providers()
    
    # Gemini deve vir antes de OpenRouter
    assert providers == ["Gemini", "OpenRouter"]


# ─────────────────────────────────────────────────────────────
#  Testes de print_llm_status()
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
def test_print_llm_status_output(env_cleanup, capsys):
    """Testa output formatado de print_llm_status()."""
    from agents.llm import print_llm_status
    
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    print_llm_status()
    
    captured = capsys.readouterr()
    output = captured.out
    
    # Verifica elementos do output
    assert "THE MOON" in output
    assert "LLM Provider Status" in output
    assert "Groq" in output
    assert "Recomendações" in output
    assert "=" in output


@pytest.mark.unit
@pytest.mark.llm_router
def test_print_llm_status_no_providers(env_cleanup, capsys):
    """Testa output quando nenhum provider está configurado."""
    from agents.llm import print_llm_status
    
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    print_llm_status()
    
    captured = capsys.readouterr()
    output = captured.out
    
    # Deve mencionar modo degradado
    assert "degradado" in output.lower() or "Nenhum" in output


# ─────────────────────────────────────────────────────────────
#  Testes de Cenários de Fallback
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
def test_fallback_chain_groq_unavailable(env_cleanup):
    """Simula cenário onde Groq está indisponível."""
    from agents.llm import LLMRouter, validate_llm_env
    
    # Apenas Groq configurado
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENROUTER_API_KEY"] = ""
    
    status = validate_llm_env()
    
    # Se Groq falhar, fallback chain só tem degraded
    assert status["fallback_chain"] == ["Groq"]


@pytest.mark.unit
@pytest.mark.llm_router
def test_fallback_chain_full_resilience(env_cleanup):
    """Simula cenário com máxima resiliência (todos providers)."""
    from agents.llm import validate_llm_env
    
    os.environ["GROQ_API_KEY"] = "test_groq_key"
    os.environ["GEMINI_API_KEY"] = "test_gemini_key"
    os.environ["OPENROUTER_API_KEY"] = "test_openrouter_key"
    
    status = validate_llm_env()
    
    # Deve ter cadeia completa de fallback
    assert len(status["fallback_chain"]) == 3
    assert status["fallback_chain"][0] == "Groq"
    assert status["fallback_chain"][1] == "Gemini"
    assert status["fallback_chain"][2] == "OpenRouter"


# ─────────────────────────────────────────────────────────────
#  Testes de Integração com Config
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.llm_router
def test_validate_uses_config_fallback():
    """Testa que validate_llm_env usa Config como fallback."""
    from agents.llm import validate_llm_env
    from core.config import Config
    
    # Simula Config com chave
    with patch('agents.llm.Config') as mock_config_class:
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key: "mock_key" if key != "llm.api_key" else "mock_groq_key"
        mock_config_class.return_value = mock_config
        
        status = validate_llm_env()
        
        # Deve usar chave do Config
        assert status["configured"]["groq"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
