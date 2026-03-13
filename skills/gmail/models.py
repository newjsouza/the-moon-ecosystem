"""
models.py - Data models for Gmail Skill
Ported from Jarvis project.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import email
from email.header import decode_header


class EmailProvider(Enum):
    """Supported email providers"""
    GMAIL = "gmail"
    ICLOUD = "icloud"
    IMAP = "imap"


class EmailFolderType(Enum):
    """Email folder types"""
    INBOX = "inbox"
    SENT = "sent"
    DRAFTS = "drafts"
    TRASH = "trash"
    SPAM = "spam"
    ARCHIVE = "archive"
    IMPORTANT = "important"
    STARRED = "starred"
    CUSTOM = "custom"


@dataclass
class EmailAttachment:
    """Represents an email attachment"""
    filename: str
    content_type: str
    size: int
    data: bytes = field(default_factory=bytes, repr=False)
    
    def save_to_file(self, path: str) -> None:
        """Save attachment to file"""
        with open(path, "wb") as f:
            f.write(self.data)


@dataclass
class EmailMessage:
    """Represents an email message"""
    id: str
    account_id: str
    provider: EmailProvider
    
    # Headers
    subject: str = ""
    from_address: str = ""
    from_name: str = ""
    to_addresses: List[str] = field(default_factory=list)
    cc_addresses: List[str] = field(default_factory=list)
    bcc_addresses: List[str] = field(default_factory=list)
    reply_to: str = ""
    
    # Content
    body_plain: str = ""
    body_html: str = ""
    attachments: List[EmailAttachment] = field(default_factory=list)
    
    # Metadata
    date: datetime = field(default_factory=datetime.now)
    received_date: datetime = field(default_factory=datetime.now)
    message_id: str = ""
    in_reply_to: str = ""
    references: List[str] = field(default_factory=list)
    
    # Status
    is_read: bool = False
    is_starred: bool = False
    is_important: bool = False
    is_draft: bool = False
    is_sent: bool = False
    
    # Organization
    folder: str = "INBOX"
    labels: List[str] = field(default_factory=list)
    thread_id: str = ""
    
    # Raw data
    raw_data: bytes = field(default_factory=bytes, repr=False)
    
    @classmethod
    def from_email_object(cls, email_obj: Any, 
                          account_id: str, provider: EmailProvider,
                          msg_id: str = "") -> "EmailMessage":
        """Create EmailMessage from email.Message object"""
        # Decoding header
        subject_raw = email_obj.get("Subject", "")
        subject = cls._decode_header(subject_raw)
        
        # Sender
        from_raw = email_obj.get("From", "")
        from_name, from_address = cls._parse_email_address(from_raw)
        
        # Recipients
        to_addresses = cls._parse_email_list(email_obj.get("To", ""))
        cc_addresses = cls._parse_email_list(email_obj.get("Cc", ""))
        bcc_addresses = cls._parse_email_list(email_obj.get("Bcc", ""))
        
        # Date
        date_raw = email_obj.get("Date", "")
        try:
            from email.utils import parsedate_to_datetime
            date = parsedate_to_datetime(date_raw)
        except (TypeError, ValueError):
            date = datetime.now()
        
        # Body and attachments
        body_plain = ""
        body_html = ""
        attachments = []
        
        if email_obj.is_multipart():
            for part in email_obj.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get_content_disposition())
                
                if content_disposition == "attachment" or "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        try:
                            data = part.get_payload(decode=True) or b""
                            attachments.append(EmailAttachment(
                                filename=filename,
                                content_type=content_type,
                                size=len(data),
                                data=data,
                            ))
                        except Exception:
                            pass
                elif content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_plain = payload.decode(charset, errors="replace")
                    except Exception:
                        pass
                elif content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body_html = payload.decode(charset, errors="replace")
                    except Exception:
                        pass
        else:
            try:
                payload = email_obj.get_payload(decode=True)
                if payload:
                    charset = email_obj.get_content_charset() or "utf-8"
                    content_type = email_obj.get_content_type()
                    if content_type == "text/html":
                        body_html = payload.decode(charset, errors="replace")
                    else:
                        body_plain = payload.decode(charset, errors="replace")
            except Exception:
                pass
        
        raw_data = email_obj.as_bytes()
        
        return cls(
            id=msg_id or email_obj.get("Message-ID", "") or "unknown",
            account_id=account_id,
            provider=provider,
            subject=subject,
            from_address=from_address,
            from_name=from_name,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            reply_to=email_obj.get("Reply-To", ""),
            body_plain=body_plain,
            body_html=body_html,
            attachments=attachments,
            date=date or datetime.now(),
            received_date=date or datetime.now(),
            message_id=email_obj.get("Message-ID", ""),
            in_reply_to=email_obj.get("In-Reply-To", ""),
            folder=email_obj.get("X-GM-LABELS", "INBOX"),
            raw_data=raw_data,
        )
    
    @staticmethod
    def _decode_header(header: str) -> str:
        if not header:
            return ""
        decoded_parts = decode_header(header)
        result = []
        for text, encoding in decoded_parts:
            if isinstance(text, bytes):
                try:
                    result.append(text.decode(encoding or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result.append(text.decode("utf-8", errors="replace"))
            else:
                result.append(text)
        return "".join(result)
    
    @staticmethod
    def _parse_email_address(address: str) -> Tuple[str, str]:
        import re
        if not address:
            return ("", "")
        match = re.match(r'"?([^"<]*)"?\s*<?([^>]+)>?', address)
        if match:
            name = match.group(1).strip()
            email_addr = match.group(2).strip()
            return (name, email_addr)
        return ("", address.strip())
    
    @staticmethod
    def _parse_email_list(addresses: str) -> List[str]:
        if not addresses:
            return []
        import re
        emails = []
        for match in re.finditer(r'[\w\.-]+@[\w\.-]+\.\w+', addresses):
            emails.append(match.group(0))
        if not emails and addresses:
            emails = [a.strip() for a in addresses.split(",") if "@" in a]
        return emails
    
    @property
    def body(self) -> str:
        return self.body_html or self.body_plain

    @property
    def preview(self) -> str:
        content = self.body_plain or self.body_html
        if len(content) > 150:
            return content[:150] + "..."
        return content

    @property
    def has_attachments(self) -> bool:
        return len(self.attachments) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "provider": self.provider.value,
            "subject": self.subject,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "to_addresses": self.to_addresses,
            "body": self.body,
            "date": self.date.isoformat() if self.date else None,
            "is_read": self.is_read,
            "is_starred": self.is_starred,
            "folder": self.folder,
            "labels": self.labels,
            "has_attachments": len(self.attachments) > 0,
        }


@dataclass
class EmailAccount:
    """Represents a configured email account"""
    id: str
    provider: EmailProvider
    email_address: str
    name: str = ""
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    last_sync: Optional[datetime] = None
    sync_status: str = "unknown"
    error_message: str = ""
    total_emails: int = 0
    unread_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider.value,
            "email_address": self.email_address,
            "name": self.name,
            "enabled": self.enabled,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "sync_status": self.sync_status,
            "unread_count": self.unread_count,
        }


@dataclass
class EmailFolder:
    """Represents an email folder/label"""
    id: str
    account_id: str
    name: str
    folder_type: EmailFolderType = EmailFolderType.CUSTOM
    parent_folder: Optional[str] = None
    message_count: int = 0
    unread_count: int = 0
    label_id: Optional[str] = None
    label_color: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "folder_type": self.folder_type.value,
            "message_count": self.message_count,
            "unread_count": self.unread_count,
        }
