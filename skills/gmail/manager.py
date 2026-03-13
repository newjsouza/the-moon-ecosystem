"""
manager.py - Gmail Skill Manager for The Moon
Orchestrates Gmail operations as a Skill.
"""

import os
import asyncio
import logging
from typing import Dict, Any, List
from pathlib import Path

from skills.skill_base import SkillBase
from skills.gmail.service import GmailService
from skills.gmail.credential_manager import CredentialManager

logger = logging.getLogger("moon.skills.gmail")

class GmailManager(SkillBase):
    """
    Skill to manage Gmail interactions.
    Supported actions: list_unread, send_email, mark_read.
    """
    
    def __init__(self):
        super().__init__(name="gmail")
        self.cred_manager = CredentialManager()
        self.service = None
        self._initialized = False

    async def _initialize_service(self) -> bool:
        """Initialize Gmail service with configured credentials"""
        if self._initialized:
            return True
            
        # Get primary Gmail credential
        creds = self.cred_manager.get_all_credentials()
        gmail_creds = [c for c in creds if c.provider == "gmail" and c.enabled]
        
        if not gmail_creds:
            logger.error("No Gmail credentials found. Run skills/gmail/setup.py first.")
            return False
            
        cred = gmail_creds[0] # Use the first one for now
        
        # Token path
        token_path = Path.home() / ".moon" / "email" / f"token_{cred.id}.json"
        
        # In The Moon, we expect client_id and client_secret in .env or stored in creds
        client_id = os.getenv("GMAIL_CLIENT_ID") or cred.client_id
        client_secret = os.getenv("GMAIL_CLIENT_SECRET") or cred.client_secret
        
        if not client_id or not client_secret:
            logger.error("GMAIL_CLIENT_ID or GMAIL_CLIENT_SECRET missing.")
            return False
            
        self.service = GmailService(
            client_id=client_id,
            client_secret=client_secret,
            token_path=str(token_path)
        )
        
        if self.service.authenticate():
            self._initialized = True
            return True
        return False

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Gmail actions.
        Params:
            action: 'list_unread', 'send_email', 'mark_read'
            limit: int (for list_unread)
            to: List[str] (for send_email)
            subject: str (for send_email)
            body: str (for send_email)
            message_ids: List[str] (for mark_read)
        """
        if not await self._initialize_service():
            return {"success": False, "error": "Authentication failed"}
            
        if self.service is None:
            return {"success": False, "error": "Service not initialized"}
            
        action = params.get("action")
        try:
            if action == "list_unread":
                limit = params.get("limit", 10)
                emails = self.service.fetch_emails(limit=limit, unread_only=True)
                return {
                    "success": True,
                    "emails": [e.to_dict() for e in emails]
                }
                
            elif action == "send_email":
                to = params.get("to", [])
                subject = params.get("subject", "No Subject")
                body = params.get("body", "")
                success = self.service.send_email(to=to, subject=subject, body=body)
                return {"success": success}
                
            elif action == "mark_read":
                message_ids = params.get("message_ids", [])
                success = self.service.mark_as_read(message_ids)
                return {"success": success}
                
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Error executing Gmail action {action}: {e}")
            return {"success": False, "error": str(e)}
