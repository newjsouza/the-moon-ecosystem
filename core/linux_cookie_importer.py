"""
core/linux_cookie_importer.py
Cookie Importer para Linux (GNOME Keyring via secretstorage)

Architecture:
  - Localiza bancos de cookies de browsers Chromium-based no Linux
  - Descriptografa via GNOME Keyring (secretstorage)
  - Retorna cookies no formato Playwright
"""
from __future__ import annotations

import glob
import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("moon.core.cookie_importer")


# ─────────────────────────────────────────────────────────────
#  Browser Paths (Linux)
# ─────────────────────────────────────────────────────────────

LINUX_BROWSER_PATHS = {
    "chrome": "~/.config/google-chrome/",
    "chromium": "~/.config/chromium/",
    "brave": "~/.config/brave-browser/",
    "edge": "~/.config/microsoft-edge/",
}


class LinuxCookieImporter:
    """Importa cookies de browsers Chromium no Linux."""
    
    def __init__(self):
        self._chrome_key: Optional[bytes] = None
    
    def find_browsers(self) -> List[str]:
        """Encontra browsers instalados."""
        installed = []
        home = os.path.expanduser("~")
        
        for name, path_template in LINUX_BROWSER_PATHS.items():
            path = os.path.expanduser(path_template)
            cookie_db = os.path.join(path, "Default", "Cookies")
            
            if os.path.exists(cookie_db):
                installed.append(name)
                logger.info(f"Found browser: {name} at {cookie_db}")
        
        return installed
    
    def get_cookies(self, browser: str, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Obtém cookies de um browser.
        
        Args:
            browser: Nome do browser (chrome, chromium, brave, edge)
            domain: Filtrar por domínio (opcional)
        
        Returns:
            Lista de cookies no formato Playwright
        """
        if browser not in LINUX_BROWSER_PATHS:
            logger.error(f"Unknown browser: {browser}")
            return []
        
        # Path do banco de cookies
        cookie_db = os.path.expanduser(
            os.path.join(LINUX_BROWSER_PATHS[browser], "Default", "Cookies")
        )
        
        if not os.path.exists(cookie_db):
            logger.error(f"Cookies not found for {browser}")
            return []
        
        # Copia para temp (evita lock do SQLite)
        temp_db = tempfile.mktemp(suffix=".db")
        try:
            shutil.copy2(cookie_db, temp_db)
            return self._read_cookies(temp_db, domain)
        except Exception as e:
            logger.error(f"Failed to read cookies: {e}")
            return []
        finally:
            if os.path.exists(temp_db):
                os.unlink(temp_db)
    
    def _read_cookies(self, db_path: str, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lê cookies do banco SQLite."""
        cookies = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Query para cookies
            query = """
                SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly, encrypted_value
                FROM cookies
            """
            params = []
            
            if domain:
                query += " WHERE host_key LIKE ?"
                params = [f"%{domain}%"]
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            for row in rows:
                name, value, host_key, path, expires_utc, is_secure, is_httponly, encrypted = row
                
                # Descriptografar se necessário
                if not value and encrypted:
                    value = self._decrypt_value(encrypted)
                
                if value:
                    cookies.append({
                        "name": name,
                        "value": value,
                        "domain": host_key.lstrip("."),
                        "path": path or "/",
                        "expires": self._chromium_to_unix(expires_utc) if expires_utc else -1,
                        "secure": bool(is_secure),
                        "httpOnly": bool(is_httponly),
                        "sameSite": "Lax",  # Default
                    })
            
            conn.close()
            logger.info(f"Read {len(cookies)} cookies from {db_path}")
            
        except Exception as e:
            logger.error(f"SQLite error: {e}")
        
        return cookies
    
    def _decrypt_value(self, encrypted: bytes) -> Optional[str]:
        """Descriptografa valor do cookie."""
        if not encrypted:
            return None
        
        # Chrome v10+ format
        if encrypted.startswith(b"v10"):
            try:
                key = self._get_chrome_key()
                if not key:
                    return None
                
                from Crypto.Cipher import AES
                
                # IV = 16 bytes de espaço
                iv = b" " * 16
                
                # Decrypt
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = cipher.decrypt(encrypted[3:])  # Remove "v10"
                
                # Remove PKCS7 padding e primeiros 32 bytes (HMAC)
                if len(decrypted) > 32:
                    return decrypted[32:].decode("utf-8", errors="ignore")
                
            except Exception as e:
                logger.warning(f"Decryption failed: {e}")
        
        return None
    
    def _get_chrome_key(self) -> Optional[bytes]:
        """Obtém chave de descriptografia do Chrome."""
        if self._chrome_key:
            return self._chrome_key
        
        try:
            import secretstorage
            
            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            collection.unlock()
            
            for item in collection.get_all_items():
                if "chrome" in item.get_label().lower() or "chromium" in item.get_label().lower():
                    self._chrome_key = item.get_secret()
                    logger.info(f"Got Chrome key from: {item.get_label()}")
                    return self._chrome_key
            
            logger.warning("Chrome Safe Storage not found in keyring")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get Chrome key: {e}")
            return None
    
    def _chromium_to_unix(self, epoch: int) -> int:
        """Converte epoch do Chromium para Unix."""
        # Chromium epoch: microseconds since 1601-01-01
        # Unix epoch: seconds since 1970-01-01
        CHROMIUM_OFFSET = 11644473600000000  # microseconds
        
        if epoch == 0:
            return -1  # Session cookie
        
        unix_micro = (epoch - CHROMIUM_OFFSET) / 1_000_000
        return int(unix_micro)


# ─────────────────────────────────────────────────────────────
#  Utility function
# ─────────────────────────────────────────────────────────────

def import_cookies_for_domain(browser: str, domain: str) -> List[Dict[str, Any]]:
    """
    Importa cookies de um domínio específico.
    
    Uso:
        cookies = import_cookies_for_domain("chrome", "example.com")
    """
    importer = LinuxCookieImporter()
    return importer.get_cookies(browser, domain)
