"""
core/channel_gateway.py
Multichannel abstraction over the existing MessageBus.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable, Awaitable
import time
import asyncio
from .message_bus import MessageBus
from .session_manager import SessionManager


@dataclass
class ChannelMessage:
    """Represents a message from any channel."""
    channel_type: str  # "telegram" | "discord" | "whatsapp" | "slack" | "cli" | "internal"
    channel_id: str
    user_id: str
    text: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ChannelResponse:
    """Represents a response to be sent back to a channel."""
    success: bool
    text: str
    channel_type: str
    channel_id: str
    metadata: Optional[Dict[str, Any]] = None


class ChannelGateway:
    """Multichannel abstraction over the MessageBus."""
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChannelGateway, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._adapters: Dict[str, Callable] = {}
        self._message_bus = MessageBus()
        self._session_manager = SessionManager()
        self._stats = {
            "messages_dispatched": 0,
            "responses_sent": 0,
            "errors": 0
        }
        self._initialized = True

    def register_adapter(self, channel_type: str, send_fn: Callable[[ChannelResponse], Awaitable[bool]]) -> None:
        """Register a send function for a specific channel type."""
        self._adapters[channel_type] = send_fn

    async def dispatch(self, message: ChannelMessage) -> str:
        """Normalizes message and publishes to MessageBus as topic 'channel.inbound'."""
        # Generate a session ID for tracking
        session_id = self._session_manager.build_session_id(
            mode="user",
            user_id=message.user_id,
            channel=message.channel_id
        )
        
        # Prepare normalized message for internal processing
        normalized = {
            "text": message.text,
            "user_id": message.user_id,
            "channel_type": message.channel_type,
            "channel_id": message.channel_id,
            "session_id": session_id,
            "timestamp": time.time(),
            "metadata": message.metadata or {}
        }
        
        # Publish to MessageBus
        await self._message_bus.publish(
            sender="ChannelGateway",
            topic="channel.inbound",
            payload=normalized
        )
        
        # Update stats
        self._stats["messages_dispatched"] += 1
        
        return session_id

    async def reply(self, response: ChannelResponse) -> bool:
        """Calls the adapter registered for the channel_type."""
        success = False
        try:
            adapter = self._adapters.get(response.channel_type)
            if adapter:
                # Call the adapter function
                success = await adapter(response)
            else:
                # Fallback: log if adapter not found, never raises exception
                import logging
                logger = logging.getLogger("moon.channel_gateway")
                logger.warning(
                    f"No adapter found for channel type: {response.channel_type}. "
                    f"Could not send response: {response.text[:100]}"
                )
                success = False
        except Exception as e:
            import logging
            logger = logging.getLogger("moon.channel_gateway")
            logger.error(f"Error in reply for channel {response.channel_type}: {e}")
            self._stats["errors"] += 1
            success = False  # Never propagate exceptions
        
        if success:
            self._stats["responses_sent"] += 1
        
        return success

    def get_registered_channels(self) -> List[str]:
        """Return list of registered channel types."""
        return list(self._adapters.keys())

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the gateway."""
        return self._stats.copy()


def get_channel_gateway() -> ChannelGateway:
    """Singleton getter for ChannelGateway."""
    return ChannelGateway()