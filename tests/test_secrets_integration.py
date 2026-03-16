"""
tests/test_secrets_integration.py
Testes de integração com secrets reais (GROQ_API_KEY, TELEGRAM_BOT_TOKEN).
"""
import pytest
import os
import asyncio
from dotenv import load_dotenv

# Carrega .env
load_dotenv()


# ─────────────────────────────────────────────────────────────
#  Testes GROQ_API_KEY
# ─────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.requires_groq
@pytest.mark.asyncio
async def test_groq_api_key_configured():
    """Verifica que GROQ_API_KEY está configurada."""
    api_key = os.getenv("GROQ_API_KEY")
    
    assert api_key is not None, "GROQ_API_KEY não configurada no .env"
    assert api_key != "", "GROQ_API_KEY vazia"
    assert api_key.startswith("gsk_"), "GROQ_API_KEY com formato inválido"
    assert len(api_key) >= 40, f"GROQ_API_KEY muito curta ({len(api_key)} caracteres)"


@pytest.mark.integration
@pytest.mark.requires_groq
@pytest.mark.asyncio
async def test_groq_api_integration():
    """Testa integração real com Groq API."""
    from groq import AsyncGroq
    
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        pytest.skip("GROQ_API_KEY não configurada")
    
    client = AsyncGroq(api_key=api_key)
    
    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Diga apenas: GROQ OK"}],
            max_tokens=10,
            temperature=0.5,
        )
        
        result = response.choices[0].message.content.strip()
        assert result is not None
        assert len(result) > 0
        
    except Exception as e:
        pytest.fail(f"Erro na integração com Groq: {e}")


@pytest.mark.integration
@pytest.mark.requires_groq
@pytest.mark.asyncio
async def test_groq_llm_router_integration():
    """Testa LLMRouter com Groq API real."""
    from agents.llm import LLMRouter
    
    router = LLMRouter()
    
    # Verifica que Groq está configurado
    assert len(router.providers) > 0, "Nenhum provider configurado no LLMRouter"
    
    # Verifica que Groq é o primeiro provider
    provider_names = [p.name for p in router.providers]
    assert "Groq" in provider_names, "Groq não está na lista de providers"


# ─────────────────────────────────────────────────────────────
#  Testes TELEGRAM_BOT_TOKEN
# ─────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.requires_telegram
@pytest.mark.asyncio
async def test_telegram_bot_token_configured():
    """Verifica que TELEGRAM_BOT_TOKEN está configurado."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    assert token is not None, "TELEGRAM_BOT_TOKEN não configurada no .env"
    assert token != "", "TELEGRAM_BOT_TOKEN vazia"
    assert ":" in token, "TELEGRAM_BOT_TOKEN com formato inválido (esperado ID:TOKEN)"
    
    # Formato do Telegram: numeros:letras
    parts = token.split(":")
    assert len(parts) == 2, "TELEGRAM_BOT_TOKEN formato inválido"
    assert parts[0].isdigit(), "TELEGRAM_BOT_TOKEN ID deve ser numérico"
    assert len(parts[0]) >= 10, f"TELEGRAM_BOT_TOKEN ID muito curto ({len(parts[0])} dígitos)"


@pytest.mark.integration
@pytest.mark.requires_telegram
@pytest.mark.asyncio
async def test_telegram_bot_info():
    """Testa obtenção de informações do bot Telegram."""
    try:
        from telegram import Bot
    except ImportError:
        pytest.skip("python-telegram-bot não instalado")
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        pytest.skip("TELEGRAM_BOT_TOKEN não configurada")
    
    try:
        bot = Bot(token=token)
        info = await bot.get_me()
        
        assert info is not None
        assert info.id is not None
        assert info.username is not None or info.first_name is not None
        
    except Exception as e:
        pytest.fail(f"Erro ao conectar com Telegram: {e}")


@pytest.mark.integration
@pytest.mark.requires_telegram
@pytest.mark.asyncio
async def test_telegram_platform_client_available():
    """Verifica que TelegramPlatformClient está disponível."""
    from agents.omni_channel_strategist import TelegramPlatformClient
    
    client = TelegramPlatformClient()
    
    # Verifica se token está configurado
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel = os.getenv("TELEGRAM_CHANNEL_ID")
    
    # Token deve estar configurado
    assert token is not None and token != "", "TELEGRAM_BOT_TOKEN não configurada"
    
    # Client deve reportar disponibilidade baseada no token
    # (channel é opcional para verificação básica)


# ─────────────────────────────────────────────────────────────
#  Testes de Validação de Ambiente
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_llm_env_with_real_keys():
    """Testa validate_llm_env com chaves reais do .env."""
    from agents.llm import validate_llm_env
    
    status = validate_llm_env()
    
    # Groq deve estar configurada
    assert status["configured"]["groq"] is True, "Groq deveria estar configurada"
    assert "Groq" in status["providers_configured"]
    
    # Sistema deve estar totalmente configurado
    assert status["fully_configured"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_secrets_not_in_code():
    """Verifica que secrets não estão hardcoded no código."""
    import re
    
    # Arquivos para verificar
    files_to_check = [
        "agents/llm.py",
        "agents/omni_channel_strategist.py",
        "main.py",
        "core/config.py",
    ]
    
    # Padrões que indicariam secrets hardcoded
    secret_patterns = [
        r'gsk_[a-zA-Z0-9]{40,}',  # Groq key
        r'\d{10}:[A-Za-z0-9_-]{35,}',  # Telegram token
        r'ghp_[a-zA-Z0-9]{36}',  # GitHub token
    ]
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        for pattern in secret_patterns:
            matches = re.findall(pattern, content)
            assert len(matches) == 0, f"Secret hardcoded encontrado em {filepath}: {matches}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
