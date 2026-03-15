"""
core/workspace/manager.py
Central manager for the workspace ecosystem.
"""
import os
import logging
from typing import Dict
from core.workspace.room import AgentRoom
from core.message_bus import MessageBus

logger = logging.getLogger("moon.workspace.manager")

class WorkspaceManager:
    def __init__(self, base_path: str = "learning/workspaces"):
        self.base_path = base_path
        self.rooms_path = os.path.join(base_path, "rooms")
        self.rooms: Dict[str, AgentRoom] = {}
        self.message_bus = MessageBus()
        
        # Ensure base structure
        os.makedirs(self.rooms_path, exist_ok=True)
        self.message_bus.subscribe("workspace.network", self._handle_network_message)
        logger.info(f"WorkspaceManager initialized at {self.base_path}")

    async def create_room(self, skill_name: str, leader_name: str) -> AgentRoom:
        """Creates a new room for a skill if it doesn't exist."""
        room_id = skill_name.lower().replace(" ", "_")
        if room_id not in self.rooms:
            room = AgentRoom(room_id, leader_name, self.rooms_path)
            self.rooms[room_id] = room
            logger.info(f"Room created: {room_id} for skill {skill_name}")
            room.log_event(f"Sala inicializada para a skill {skill_name}. Bem-vindo, {leader_name}!")
        return self.rooms[room_id]

    async def _handle_network_message(self, message):
        """Standard handler for inter-room communication."""
        sender = message.sender
        topic = message.topic
        payload = message.payload
        target = message.target
        
        if target and target in self.rooms:
            self.rooms[target].log_event(f"Mensagem recebida de {sender}: {payload}")
        elif not target:
            # Broadcast to all rooms
            for room in self.rooms.values():
                if room.room_id != sender:
                    room.log_event(f"Broadcast de {sender}: {payload}")

    def get_all_rooms_status(self) -> Dict[str, dict]:
        return {room_id: room.get_status() for room_id, room in self.rooms.items()}
