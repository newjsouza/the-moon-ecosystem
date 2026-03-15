"""
service.py - Supabase Service integration
Interfaces with the Supabase MCP server tools.
"""

import logging
from typing import List, Optional, Dict, Any
from .models import DBRecord, NeuralLinkLog

logger = logging.getLogger(__name__)

class SupabaseService:
    """
    Service to interact with Supabase using MCP tools.
    Provides methods for CRUD and logging.
    """
    
    def __init__(self, project_id: str = "ntrgbqvywscifjcdwwyb"):
        self.project_id = project_id

    async def log_event(self, event_type: str, agent: str, payload: Dict[str, Any], error: Optional[str] = None):
        """Logs an event to neural_link_logs using execute_sql"""
        # SQL handled by the manager proxy
        pass

    def parse_log(self, data: Dict[str, Any]) -> NeuralLinkLog:
        """Parses log data from Supabase format"""
        return NeuralLinkLog(
            id=data.get("id"),
            event_type=data.get("event_type", ""),
            agent_sender=data.get("agent_sender", ""),
            message_payload=data.get("message_payload", {}),
            error_details=data.get("error_details"),
            timestamp=data.get("timestamp")
        )
