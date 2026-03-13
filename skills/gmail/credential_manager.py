"""
credential_manager.py - Secure storage for email tokens
Adapted from Jarvis project for The Moon (Linux environment).
"""

import os
import json
import base64
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

@dataclass
class EmailCredential:
    """Email Credential"""
    id: str
    provider: str  # gmail, icloud
    email_address: str
    name: str = ""
    enabled: bool = True
    
    # Auth
    auth_type: str = "oauth2"  # oauth2, app_password
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: Optional[str] = None  # ISO format
    app_password: str = ""
    
    # OAuth2 config (Gmail)
    client_id: str = ""
    client_secret: str = ""
    scopes: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None
    
    # Status
    status: str = "unknown"
    error_message: str = ""
    
    def is_token_valid(self) -> bool:
        if not self.token_expiry:
            return False
        try:
            expiry = datetime.fromisoformat(self.token_expiry)
            return datetime.now() < expiry - timedelta(minutes=5)
        except ValueError:
            return False

class CredentialManager:
    """
    Manages credentials using an encrypted file.
    Uses XOR + Base64 encryption with a key derived from the system user.
    """

    def __init__(self, vault_path: Optional[str] = None):
        if vault_path:
            self.vault_path = Path(vault_path)
        else:
            # Default location in The Moon project
            self.vault_path = Path.home() / ".moon" / "email" / "vault.json"
        
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, EmailCredential] = {}
        self._load_credentials()

    def _get_encryption_key(self) -> bytes:
        """Derive a key from the system login"""
        try:
            user = os.getlogin()
        except:
            # Fallback for environments where getlogin fails
            user = os.getenv("USER", "moon_user")
        return hashlib.sha256(user.encode()).digest()

    def _encrypt(self, data: bytes) -> bytes:
        """Encrypt data using XOR + Base64"""
        key = self._get_encryption_key()
        key_len = len(key)
        encrypted = bytes([data[i] ^ key[i % key_len] for i in range(len(data))])
        return base64.b64encode(encrypted)

    def _decrypt(self, data: bytes) -> bytes:
        """Decrypt data using XOR + Base64"""
        key = self._get_encryption_key()
        key_len = len(key)
        decoded = base64.b64decode(data)
        decrypted = bytes([decoded[i] ^ key[i % key_len] for i in range(len(decoded))])
        return decrypted

    def _load_credentials(self) -> None:
        if not self.vault_path.exists():
            return
        try:
            with open(self.vault_path, 'rb') as f:
                encrypted_data = f.read()
            decrypted_data = self._decrypt(encrypted_data)
            vault_data = json.loads(decrypted_data.decode('utf-8'))
            for cid, cdata in vault_data.items():
                if isinstance(cdata.get('scopes'), str):
                    cdata['scopes'] = json.loads(cdata['scopes'])
                self._cache[cid] = EmailCredential(**cdata)
            logger.info(f"Loaded {len(self._cache)} credentials from vault")
        except Exception as e:
            logger.error(f"Error loading vault: {e}")

    def _save_credentials(self) -> None:
        try:
            vault_data = {cid: asdict(cred) for cid, cred in self._cache.items()}
            json_data = json.dumps(vault_data).encode('utf-8')
            encrypted_data = self._encrypt(json_data)
            with open(self.vault_path, 'wb') as f:
                f.write(encrypted_data)
            os.chmod(self.vault_path, 0o600)  # Restricted permissions
            logger.info(f"Credentials saved to {self.vault_path}")
        except Exception as e:
            logger.error(f"Error saving vault: {e}")

    def add_credential(self, credential: EmailCredential) -> bool:
        credential.updated_at = datetime.now().isoformat()
        self._cache[credential.id] = credential
        self._save_credentials()
        return True

    def get_credential(self, credential_id: str) -> Optional[EmailCredential]:
        return self._cache.get(credential_id)

    def get_all_credentials(self) -> List[EmailCredential]:
        return list(self._cache.values())

    def update_token(self, credential_id: str, access_token: str, refresh_token: str = "", expires_in: int = 3600) -> bool:
        cred = self.get_credential(credential_id)
        if not cred: return False
        cred.access_token = access_token
        if refresh_token: cred.refresh_token = refresh_token
        cred.token_expiry = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
        cred.status = "active"
        cred.updated_at = datetime.now().isoformat()
        self._save_credentials()
        return True
