"""
core/security/audit.py
SecurityAuditLog — Log de auditoria append-only.

Registra todas as ações críticas em formato JSONL para análise forense.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import threading

logger = logging.getLogger(__name__)


class SecurityAuditLog:
    """
    Log de auditoria de segurança.
    
    Todas as ações críticas são registradas em formato JSONL
    (uma entrada por linha) para facilitar análise e parsing.
    """
    
    _instance: Optional["SecurityAuditLog"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "SecurityAuditLog":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
        self._log_dir.mkdir(exist_ok=True)
        self._log_file = self._log_dir / "security.jsonl"
        self._initialized = True
        
        logger.info("SecurityAuditLog iniciado: %s", self._log_file)
    
    def log_action(
        self,
        action: str,
        actor: str,
        resource: Optional[str] = None,
        status: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Registra uma ação no log de auditoria.
        
        Args:
            action: Tipo de ação (ex: "login", "command_exec", "secret_access").
            actor: Quem executou a ação (ex: user_id, agent_name).
            resource: Recurso afetado (ex: file path, command).
            status: "success" ou "failure".
            metadata: Dados adicionais (ex: {"ip": "...", "reason": "..."}).
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "resource": resource,
            "status": status,
            "metadata": metadata or {},
        }
        
        with self._lock:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error("Falha ao escrever audit log: %s", e)
    
    def log_success(
        self,
        action: str,
        actor: str,
        resource: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log de ação bem-sucedida."""
        self.log_action(action, actor, resource, status="success", metadata=metadata)
    
    def log_failure(
        self,
        action: str,
        actor: str,
        resource: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log de ação falhada/bloqueada."""
        meta = metadata or {}
        if reason:
            meta["reason"] = reason
        self.log_action(action, actor, resource, status="failure", metadata=meta)
    
    def log_command_exec(
        self,
        actor: str,
        command: str,
        status: str = "success",
        output_preview: Optional[str] = None,
    ) -> None:
        """Log de execução de comando."""
        metadata = {"command": command}
        if output_preview:
            metadata["output_preview"] = output_preview[:500]  # Truncar
        self.log_action("command_exec", actor, resource=command, status=status, metadata=metadata)
    
    def log_secret_access(
        self,
        actor: str,
        secret_name: str,
        granted: bool,
    ) -> None:
        """Log de acesso a secret."""
        status = "success" if granted else "failure"
        self.log_action(
            "secret_access",
            actor,
            resource=secret_name,
            status=status,
            metadata={"granted": granted},
        )
    
    def log_auth_attempt(
        self,
        actor: str,
        granted: bool,
        reason: Optional[str] = None,
    ) -> None:
        """Log de tentativa de autenticação/autorização."""
        status = "success" if granted else "failure"
        self.log_action(
            "auth_attempt",
            actor,
            status=status,
            metadata={"granted": granted, "reason": reason},
        )
    
    def get_recent_entries(self, limit: int = 100) -> list:
        """
        Lê as últimas entradas do log.
        
        Args:
            limit: Número máximo de entradas a retornar.
            
        Returns:
            Lista de entradas (mais recentes primeiro).
        """
        entries = []
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            return []
        
        return entries[-limit:][::-1]  # Inverter para mais recentes primeiro
    
    def count_entries(self) -> int:
        """Retorna número total de entradas no log."""
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except FileNotFoundError:
            return 0
