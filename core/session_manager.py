from __future__ import annotations
from dataclasses import dataclass
import time
from typing import Any, Dict
import threading


@dataclass
class SessionEntry:
    data: Dict[str, Any]
    mode: str
    created_at: float
    expires_at: float


class SessionManager:
    def __init__(self, default_ttl: int = 3600):
        self._sessions: Dict[str, SessionEntry] = {}
        self._default_ttl = default_ttl
        self._lock = threading.RLock()

    def get_session(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return {}
            
            if time.time() > entry.expires_at:
                del self._sessions[session_id]
                return {}
            
            return entry.data.copy()

    def set_session(self, session_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            ttl = data.get('_ttl', self._default_ttl)
            expires_at = time.time() + ttl
            
            # Remover o _ttl do dado armazenado
            session_data = data.copy()
            session_data.pop('_ttl', None)
            
            self._sessions[session_id] = SessionEntry(
                data=session_data,
                mode=data.get('_mode', 'user'),
                created_at=time.time(),
                expires_at=expires_at
            )

    def build_session_id(self, mode: str, user_id: str = "", channel: str = "", workspace: str = "") -> str:
        if mode == "user":
            return f"user:{user_id}"
        elif mode == "channel":
            return f"channel:{channel}"
        elif mode == "workspace":
            return f"workspace:{workspace}"
        elif mode == "global":
            return "global:default"
        else:
            # fallback para user se o modo for inválido
            return f"user:{user_id}"

    def clear_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired_keys = []
            
            for session_id, entry in self._sessions.items():
                if now > entry.expires_at:
                    expired_keys.append(session_id)
            
            for key in expired_keys:
                del self._sessions[key]
            
            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._sessions)
            modes = {"user": 0, "channel": 0, "workspace": 0, "global": 0}
            expired_count = 0
            now = time.time()
            
            for entry in self._sessions.values():
                if now > entry.expires_at:
                    expired_count += 1
                if entry.mode in modes:
                    modes[entry.mode] += 1
            
            return {
                "total": total,
                "by_mode": modes,
                "expired": expired_count
            }


# Singleton instance
_session_manager = None
_lock = threading.Lock()


def get_session_manager(default_ttl: int = 3600) -> SessionManager:
    global _session_manager
    
    with _lock:
        if _session_manager is None:
            _session_manager = SessionManager(default_ttl=default_ttl)
    
    return _session_manager