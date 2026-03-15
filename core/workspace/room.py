"""
core/workspace/room.py
Defines the AgentRoom structure for collaboration.
"""
import os
import logging
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger("moon.workspace.room")

class AgentRoom:
    def __init__(self, room_id: str, leader_name: str, base_path: str):
        self.room_id = room_id
        self.leader_name = leader_name
        self.path = os.path.join(base_path, room_id)
        self.computer_path = os.path.join(self.path, "computer")
        self.sub_agents: List[str] = []
        self.meeting_active = False
        
        # Ensure directories exist
        os.makedirs(self.computer_path, exist_ok=True)
        self._init_logs()

    def _init_logs(self):
        log_file = os.path.join(self.path, "meeting_log.md")
        if not os.path.exists(log_file):
            with open(log_file, "w") as f:
                f.write(f"# Sala de Reunião: {self.room_id}\n")
                f.write(f"**Líder:** {self.leader_name}\n")
                f.write(f"**Criada em:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("## Histórico de Reuniões\n")

    def add_sub_agent(self, agent_name: str):
        if agent_name not in self.sub_agents:
            self.sub_agents.append(agent_name)
            logger.info(f"Sub-agente {agent_name} adicionado à sala {self.room_id}")

    def log_event(self, event: str):
        log_file = os.path.join(self.path, "meeting_log.md")
        with open(log_file, "a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {event}\n")

    def get_status(self) -> dict:
        return {
            "room_id": self.room_id,
            "leader": self.leader_name,
            "sub_agents": self.sub_agents,
            "meeting_active": self.meeting_active,
            "computer_ready": os.path.exists(self.computer_path)
        }
