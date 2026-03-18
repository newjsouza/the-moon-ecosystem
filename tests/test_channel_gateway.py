import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.channel_gateway import ChannelGateway, ChannelMessage, ChannelResponse, get_channel_gateway
from core.message_bus import MessageBus


def test_channel_message_creation():
    """Testa a criação de ChannelMessage com campos obrigatórios e defaults."""
    msg = ChannelMessage(
        channel_type="telegram",
        channel_id="12345",
        user_id="user123",
        text="Hello, world!"
    )
    
    assert msg.channel_type == "telegram"
    assert msg.channel_id == "12345"
    assert msg.user_id == "user123"
    assert msg.text == "Hello, world!"
    assert msg.metadata is None


def test_channel_response_creation():
    """Testa a criação de ChannelResponse com campos obrigatórios e defaults."""
    resp = ChannelResponse(
        success=True,
        text="Reply message",
        channel_type="telegram",
        channel_id="12345"
    )
    
    assert resp.success is True
    assert resp.text == "Reply message"
    assert resp.channel_type == "telegram"
    assert resp.channel_id == "12345"
    assert resp.metadata is None


def test_gateway_singleton():
    """Testa o singleton do gateway."""
    gateway1 = get_channel_gateway()
    gateway2 = get_channel_gateway()
    
    assert gateway1 is gateway2
    assert isinstance(gateway1, ChannelGateway)


def test_register_adapter():
    """Testa o registro de adapter e verificação da lista."""
    async def dummy_adapter(response):
        return True
    
    gateway = get_channel_gateway()
    gateway.register_adapter("telegram", dummy_adapter)
    
    assert "telegram" in gateway._adapters
    assert gateway._adapters["telegram"] == dummy_adapter


def test_get_registered_channels():
    """Testa o retorno dos canais registrados."""
    async def dummy_adapter(response):
        return True
    
    gateway = get_channel_gateway()
    gateway.register_adapter("telegram", dummy_adapter)
    gateway.register_adapter("discord", dummy_adapter)
    
    channels = gateway.get_registered_channels()
    assert "telegram" in channels
    assert "discord" in channels
    assert len(channels) == 2


def test_dispatch_publishes_to_bus():
    """Testa se dispatch() publica no MessageBus."""
    # Create a new instance of MessageBus to avoid conflicts with other tests
    bus = MessageBus()
    gateway = get_channel_gateway()
    # Replace the internal message bus for this test
    original_bus = gateway._message_bus
    gateway._message_bus = bus
    
    # Clear history to start fresh
    bus.reset()
    
    try:
        message = ChannelMessage(
            channel_type="telegram",
            channel_id="12345",
            user_id="user123",
            text="Test message"
        )
        
        session_id = asyncio.run(gateway.dispatch(message))
        
        # Verify that the message was published to the bus
        history = bus.get_history()
        assert len(history) == 1
        assert history[0].topic == "channel.inbound"
        assert history[0].payload["text"] == "Test message"
        assert history[0].payload["user_id"] == "user123"
        assert history[0].payload["channel_type"] == "telegram"
        assert history[0].payload["session_id"] == session_id
    finally:
        # Restore original message bus
        gateway._message_bus = original_bus


def test_reply_calls_adapter():
    """Testa se reply() chama o adapter correto."""
    # Mock adapter function
    async def mock_adapter(response):
        return True
    
    gateway = get_channel_gateway()
    gateway.register_adapter("telegram", mock_adapter)
    
    response = ChannelResponse(
        success=True,
        text="Test reply",
        channel_type="telegram",
        channel_id="12345"
    )
    
    # Since our adapter returns True, reply should return True
    result = asyncio.run(gateway.reply(response))
    assert result is True


def test_reply_no_adapter_fallback():
    """Testa se reply() não levanta exceção quando adapter não existe."""
    gateway = get_channel_gateway()
    # Don't register any adapter
    
    response = ChannelResponse(
        success=True,
        text="Test reply",
        channel_type="nonexistent",
        channel_id="12345"
    )
    
    # Should not raise exception and return False
    result = asyncio.run(gateway.reply(response))
    assert result is False


def test_get_stats():
    """Testa se stats retorna estrutura correta."""
    gateway = get_channel_gateway()
    stats = gateway.get_stats()
    
    assert isinstance(stats, dict)
    assert "messages_dispatched" in stats
    assert "responses_sent" in stats
    assert "errors" in stats
    # Stats should be a dictionary with the expected keys, values may vary depending on other tests
    assert isinstance(stats["messages_dispatched"], int)
    assert isinstance(stats["responses_sent"], int)
    assert isinstance(stats["errors"], int)


def test_orchestrator_channel_gateway():
    """Testa se o gateway está inicializado no Orchestrator."""
    from core.orchestrator import Orchestrator
    
    orchestrator = Orchestrator()
    
    # Check if channel_gateway is initialized
    assert hasattr(orchestrator, 'channel_gateway')
    assert orchestrator.channel_gateway is not None
    assert isinstance(orchestrator.channel_gateway, ChannelGateway)
    
    # Check if telegram adapter is registered
    assert "telegram" in orchestrator.channel_gateway.get_registered_channels()