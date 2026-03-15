"""
manager.py - Supabase Skill Manager for The Moon
Orchestrates database operations.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from skills.skill_base import SkillBase
from .service import SupabaseService

logger = logging.getLogger("moon.skills.supabase")

class SupabaseManager(SkillBase):
    """
    Skill to manage Supabase database operations.
    Acts as a proxy to the Supabase MCP server.
    """
    
    def __init__(self, project_id: str = "ntrgbqvywscifjcdwwyb"):
        super().__init__(name="supabase")
        self.service = SupabaseService(project_id=project_id)

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Supabase actions.
        Actions: 'execute_sql', 'list_tables', 'log_event', 'get_performance'.
        """
        action = params.get("action")
        project_id = self.service.project_id
        
        try:
            if action == "execute_sql":
                query = params.get("query")
                if not query:
                    return {"success": False, "error": "Query is required"}
                
                return {
                    "success": True,
                    "proxy_to": "mcp_supabase-mcp-server_execute_sql",
                    "args": {"project_id": project_id, "query": query}
                }
                
            elif action == "log_event":
                event_type = params.get("event_type", "INFO")
                agent = params.get("agent", "TheMoon")
                payload = params.get("payload", {})
                error = params.get("error")
                
                # Construct SQL for insert
                payload_json = json.dumps(payload).replace("'", "''")
                error_sql = f"'{error}'" if error else "NULL"
                
                sql = f"INSERT INTO public.neural_link_logs (event_type, agent_sender, message_payload, error_details) VALUES ('{event_type}', '{agent}', '{payload_json}'::jsonb, {error_sql});"
                
                return {
                    "success": True,
                    "proxy_to": "mcp_supabase-mcp-server_execute_sql",
                    "args": {"project_id": project_id, "query": sql}
                }

            elif action == "list_tables":
                return {
                    "success": True,
                    "proxy_to": "mcp_supabase-mcp-server_list_tables",
                    "args": {"project_id": project_id, "schemas": ["public"], "verbose": True}
                }
                
            elif action == "get_performance":
                agent_name = params.get("agent_name")
                where_clause = f"WHERE agent_name = '{agent_name}'" if agent_name else ""
                sql = f"SELECT * FROM public.agent_performance {where_clause} ORDER BY win_rate DESC;"
                
                return {
                    "success": True,
                    "proxy_to": "mcp_supabase-mcp-server_execute_sql",
                    "args": {"project_id": project_id, "query": sql}
                }
                
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Error executing Supabase action {action}: {e}")
            return {"success": False, "error": str(e)}
