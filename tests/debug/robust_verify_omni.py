
import asyncio
import os
import json
import time
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import asdict
from pathlib import Path

# Mock environment before importing agent
os.environ["TELEGRAM_BOT_TOKEN"] = "mock_token"
os.environ["TELEGRAM_CHANNEL_ID"] = "@mock_channel"
os.environ["TWITTER_API_KEY"] = "mock"
os.environ["TWITTER_API_SECRET"] = "mock"
os.environ["TWITTER_ACCESS_TOKEN"] = "mock"
os.environ["TWITTER_ACCESS_SECRET"] = "mock"
os.environ["LINKEDIN_ACCESS_TOKEN"] = "mock"
os.environ["LINKEDIN_PERSON_URN"] = "mock_urn"

from agents.omni_channel_strategist import (
    OmniChannelStrategist, Platform, ContentPiece, ContentType, PostStatus, STRATEGIST_DIR
)

async def test_robust_lifecycle():
    print("\n🔍 Iniciando Testes Robustos de Ciclo de Vida...")
    
    # Setup
    mock_bus = AsyncMock()
    mock_groq = AsyncMock()
    # Mock completion response
    mock_groq.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Texto adaptado via LLM Robust Test http://link.com"))]
    )

    agent = OmniChannelStrategist(groq_client=mock_groq, message_bus=mock_bus)
    
    # Test 1: Initialization and Subscription
    await agent.initialize()
    print("✅ Inicialização e Subscrição OK")
    
    # Test 2: Reaction to MessageBus event
    test_event = {
        "title": "Post Robusto",
        "summary": "Um resumo de teste robusto que deve ser processado.",
        "url": "https://themoon.cloud/robust-test",
        "content_type": "blog_post"
    }
    
    # Manually trigger the callback
    await agent._on_content_published(test_event)
    
    # Check if something was scheduled
    status = await agent._execute("status")
    queue_size = status.data["queue_size"]
    print(f"✅ Agendamento via MessageBus OK (Fila: {queue_size})")
    assert queue_size > 0
    
    # Test 3: Thread Splitting Edge Case (Exact limit and overflows)
    print("⏳ Testando Thread Splitting com texto longo...")
    long_text = "X" * 260 + " Y" * 50 # Over total limits
    thread = agent._adapter._split_twitter_thread(long_text, "https://link.com")
    print(f"✅ Thread gerada com {len(thread)} partes.")
    assert len(thread) > 1
    for i, t in enumerate(thread):
        assert len(t) <= 280
        if i == len(thread) - 1:
            assert "https://link.com" in t
            
    # Test 4: Persistence Test
    print("⏳ Verificando Persistência...")
    # Add a fingerprint manually or via distribute
    agent._fingerprints.add("robust_fingerprint_123")
    await agent.shutdown()
    
    # Verify file exists and has the fingerprint
    with open(STRATEGIST_DIR / "post_history.json", "r") as f:
        data = json.load(f)
        assert "robust_fingerprint_123" in data["fingerprints"]
    print("✅ Persistência de Fingerprints OK")
    
    # Reload agent
    new_agent = OmniChannelStrategist(groq_client=mock_groq, message_bus=mock_bus)
    await new_agent.initialize()
    assert "robust_fingerprint_123" in new_agent._fingerprints
    print("✅ Reload de Estado OK")
    
    # Test 5: Error Handling during Distribution
    print("⏳ Testando Resiliência a Erros de Plataforma...")
    # Mock Telegram to fail
    with patch("telegram.Bot") as mock_bot_class:
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = Exception("Conexão recusada")
        mock_bot_class.return_value = mock_bot
        
        # This shouldn't crash the whole process
        piece = ContentPiece(
            id="error_test", title="Error", summary="Err", 
            url="http://err.com", content_type=ContentType.GENERAL, source_agent="test"
        )
        res = await new_agent._distribute_now(piece)
        telegram_res = res.data["results"]["telegram"]
        print(f"✅ Falha graciosa no Telegram: {telegram_res['status']} ({telegram_res.get('error')})")
        assert telegram_res["status"] == "failed" or telegram_res["status"] == "error"

    await new_agent.shutdown()
    print("🏆 Todos os testes robustos passaram!")

if __name__ == "__main__":
    asyncio.run(test_robust_lifecycle())
