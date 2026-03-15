"""
models.py - Data models for Supabase Skill
Definitions for database records and logs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

@dataclass
class DBRecord:
    """Represents a generic database record"""
    table_name: str
    data: Dict[str, Any]
    id: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table_name,
            "id": self.id,
            "data": self.data,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

@dataclass
class NeuralLinkLog:
    """Represents a log entry in public.neural_link_logs"""
    event_type: str
    agent_sender: str
    message_payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    id: Optional[str] = None
    error_details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "agent_sender": self.agent_sender,
            "message_payload": self.message_payload,
            "error_details": self.error_details
        }
