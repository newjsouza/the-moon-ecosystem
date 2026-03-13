"""
service.py - Gmail Service integration
Adapted from Jarvis project for The Moon.
"""

import os
import base64
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from skills.gmail.models import EmailMessage, EmailFolder, EmailAccount, EmailProvider, EmailAttachment, EmailFolderType

logger = logging.getLogger(__name__)

class GmailService:
    """Service for interaction with Gmail via API and OAuth2"""
    
    def __init__(self, client_id: str, client_secret: str, token_path: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_path = Path(token_path)
        self.account: Optional[EmailAccount] = None
        self._api_client = None
        self._authenticated = False
        
        # Scopes required for full access
        self.scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.modify",
        ]

    def authenticate(self) -> bool:
        """Authenticate with Gmail using OAuth2"""
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            
            creds = None
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing OAuth2 token...")
                    creds.refresh(Request())
                    with open(self.token_path, "w") as token_file:
                        token_file.write(creds.to_json())
                else:
                    logger.error("OAuth2 credentials not found or expired. Run setup.py.")
                    return False
            
            self._api_client = build("gmail", "v1", credentials=creds)
            profile = self._api_client.users().getProfile(userId="me").execute()
            
            self.account = EmailAccount(
                id=f"gmail_{profile['emailAddress']}",
                provider=EmailProvider.GMAIL,
                email_address=profile["emailAddress"],
                name=profile.get("displayName", ""),
                sync_status="success",
                total_emails=int(profile.get("messagesTotal", 0)),
                unread_count=int(profile.get("messagesUnread", 0)),
            )
            
            self._authenticated = True
            logger.info(f"Gmail authenticated: {self.account.email_address}")
            return True
            
        except Exception as e:
            logger.error(f"Gmail authentication error: {e}")
            return False

    def fetch_emails(self, limit: int = 20, folder: str = "INBOX", unread_only: bool = False, query: str = "") -> List[EmailMessage]:
        if not self._authenticated or not self._api_client:
            return []
        try:
            full_query = query
            if unread_only:
                full_query = "is:unread " + full_query if full_query else "is:unread"
            
            results = self._api_client.users().messages().list(
                userId="me", q=full_query, maxResults=limit
            ).execute()
            
            messages = results.get("messages", [])
            emails = []
            for msg in messages:
                email_msg = self.get_email(msg["id"])
                if email_msg:
                    emails.append(email_msg)
            return emails
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []

    def get_email(self, message_id: str) -> Optional[EmailMessage]:
        try:
            raw_message = self._api_client.users().messages().get(
                userId="me", id=message_id, format="raw"
            ).execute()
            
            msg_bytes = base64.urlsafe_b64decode(raw_message["raw"])
            email_obj = email.message_from_bytes(msg_bytes)
            
            email_msg = EmailMessage.from_email_object(
                email_obj=email_obj,
                account_id=self.account.id if self.account else "",
                provider=EmailProvider.GMAIL,
                msg_id=message_id,
            )
            
            labels = raw_message.get("labelIds", [])
            email_msg.is_read = "UNREAD" not in labels
            email_msg.labels = labels
            email_msg.thread_id = raw_message.get("threadId", "")
            
            return email_msg
        except Exception as e:
            logger.error(f"Error getting email {message_id}: {e}")
            return None

    def send_email(self, to: List[str], subject: str, body: str, body_html: Optional[str] = None) -> bool:
        if not self._authenticated or not self.account or not self._api_client:
            return False
        try:
            message = MIMEMultipart("alternative")
            message["to"] = ", ".join(to)
            message["from"] = self.account.email_address
            message["subject"] = subject
            
            message.attach(MIMEText(body, "plain", "utf-8"))
            if body_html:
                message.attach(MIMEText(body_html, "html", "utf-8"))
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            self._api_client.users().messages().send(
                userId="me", body={"raw": raw_message}
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def mark_as_read(self, message_ids: List[str]) -> bool:
        try:
            for msg_id in message_ids:
                self._api_client.users().messages().modify(
                    userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
                ).execute()
            return True
        except Exception as e:
            logger.error(f"Error marking as read: {e}")
            return False
