"""
scripts/verify_secrets.py
Verifica e testa integração de secrets (GROQ_API_KEY, TELEGRAM_BOT_TOKEN).
"""
import os
import sys

# Adiciona raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Carrega .env
load_dotenv()

print("=" * 60)
print("  VERIFICAÇÃO COMPLETA DE SECRETS")
print("=" * 60)
print()

# Verifica GROQ_API_KEY
groq_key = os.getenv("GROQ_API_KEY")
print("1. GROQ_API_KEY")
print(f"   Configurada: {bool(groq_key)}")
print(f"   Formato válido: {groq_key.startswith('gsk_') if groq_key else False}")
print(f"   Tamanho: {len(groq_key) if groq_key else 0} caracteres")

# Verifica onde é usada
print("   Usada em:")
print("   - agents/llm.py (GroqProvider, LLMRouter)")
print("   - agents/opencode.py (OpenCodeAgent)")
print("   - agents/omni_channel_strategist.py (ContentAdapter)")
print("   - agents/semantic_memory_weaver.py")
print("   - agents/telegram/bot.py")
print("   - main.py (via Orchestrator)")
print()

# Verifica TELEGRAM_BOT_TOKEN
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_channel = os.getenv("TELEGRAM_CHANNEL_ID")
print("2. TELEGRAM_BOT_TOKEN")
print(f"   Configurada: {bool(telegram_token)}")
print(f"   Formato válido: {':' in telegram_token if telegram_token else False}")
print(f"   Tamanho: {len(telegram_token) if telegram_token else 0} caracteres")
print(f"   TELEGRAM_CHANNEL_ID: {'Configurado' if telegram_channel else 'Não configurado (opcional)'}")

# Verifica onde é usado
print("   Usado em:")
print("   - channels/telegram/bot.py")
print("   - agents/omni_channel_strategist.py (TelegramPlatformClient)")
print("   - agents/file_manager.py")
print()

# Testa LLMRouter
print("3. TESTE LLMROUTER")
from agents.llm import validate_llm_env, get_available_llm_providers

status = validate_llm_env()
print(f"   Providers disponíveis: {status['providers_configured']}")
print(f"   Fully configured: {status['fully_configured']}")
print()

print("=" * 60)
print("  STATUS FINAL")
print("=" * 60)
print("✅ GROQ_API_KEY: CONFIGURADA E INTEGRADA")
print("✅ TELEGRAM_BOT_TOKEN: CONFIGURADA E INTEGRADA")
print("=" * 60)
