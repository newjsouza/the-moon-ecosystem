"""
core/workspace/network.py
Implements the Local Network (5G/Intranet) for agents.
"""
import logging
from core.message_bus import MessageBus

logger = logging.getLogger("moon.workspace.network")

class AgentNetwork:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.topic = "workspace.network"

    async def send_data(self, sender: str, data: any, target: str = None):
        """Sends data across the local network."""
        logger.info(f"Network: {sender} sending data to {target or 'all'}")
        await self.bus.publish(
            sender=sender,
            topic=self.topic,
            payload=data,
            target=target
        )

    async def broadcast_status(self, sender: str, status: str):
        """Broadcasts agent status to the entire network."""
        await self.send_data(sender, {"type": "status_update", "status": status})

    async def request_service(self, requester: str, provider: str, service_name: str, params: dict):
        """Simulates a service request between agents."""
        await self.send_data(requester, {
            "type": "service_request",
            "service": service_name,
            "params": params
        }, target=provider)
