"""
base.py - Base class for communication channels
Standardizes input/output for different platforms (Terminal, Telegram, etc.)
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("moon.channels.base")

class ChannelBase(ABC):
    """
    Abstract base class for all communication channels.
    Channels are interfaces that 'The Moon' uses to interact with the world.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.on_message_received: Optional[Callable[[str, Dict[str, Any]], Any]] = None

    @abstractmethod
    async def start(self) -> None:
        """Starts the channel listener"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stops the channel listener"""
        pass

    @abstractmethod
    async def send_message(self, text: str, recipient_id: Optional[str] = None, **kwargs) -> bool:
        """Sends a message through the channel"""
        return False

    def set_callback(self, callback: Callable[[str, Dict[str, Any]], Any]) -> None:
        """Registers a callback for incoming messages"""
        self.on_message_received = callback

    async def handle_incoming(self, text: str, metadata: Dict[str, Any]) -> None:
        """Generic handler to trigger the registered callback"""
        if self.on_message_received is not None:
            await self.on_message_received(text, metadata)
        else:
            logger.warning(f"No callback registered for channel {self.name}")
