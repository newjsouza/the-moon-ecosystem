"""
core/security/rate_limiter.py
RateLimiter — Limitação de taxa de requisições.

Previne abuso e DoS acidental limitando chamadas por janela de tempo.
"""
import time
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuração de rate limit para um actor."""
    max_calls: int
    window_seconds: float
    created_at: float = field(default_factory=time.time)


class RateLimiter:
    """
    Rate limiter com janela deslizante.
    
    Limita número de chamadas por actor dentro de uma janela de tempo.
    Thread-safe para uso em aplicações async.
    """
    
    _instance: Optional["RateLimiter"] = None
    
    def __new__(cls) -> "RateLimiter":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        # actor_id -> deque de timestamps
        self._calls: Dict[str, deque] = defaultdict(deque)
        # actor_id -> config
        self._configs: Dict[str, RateLimitConfig] = {}
        # Configuração global default
        self._default_max_calls = 60
        self._default_window_seconds = 60.0
        self._initialized = True
        
        logger.info("RateLimiter iniciado (default: %d calls / %.0fs)",
                    self._default_max_calls, self._default_window_seconds)
    
    def set_limit(
        self,
        actor: str,
        max_calls: int,
        window_seconds: float,
    ) -> None:
        """
        Define limite específico para um actor.
        
        Args:
            actor: Identificador do actor (user_id, agent_name, etc.).
            max_calls: Número máximo de chamadas na janela.
            window_seconds: Tamanho da janela em segundos.
        """
        self._configs[actor] = RateLimitConfig(
            max_calls=max_calls,
            window_seconds=window_seconds,
        )
        logger.debug("Rate limit definido para %s: %d calls / %.0fs",
                     actor, max_calls, window_seconds)
    
    def check(self, actor: str) -> bool:
        """
        Verifica se actor pode fazer uma chamada (sem registrar).
        
        Args:
            actor: Identificador do actor.
            
        Returns:
            True se permitido, False se limit excedido.
        """
        config = self._get_config(actor)
        calls = self._calls[actor]
        now = time.time()
        
        # Remove chamadas fora da janela
        window_start = now - config.window_seconds
        while calls and calls[0] < window_start:
            calls.popleft()
        
        allowed = len(calls) < config.max_calls
        
        if not allowed:
            logger.warning(
                "Rate limit excedido para %s: %d/%d calls em %.0fs",
                actor, len(calls), config.max_calls, config.window_seconds
            )
        
        return allowed
    
    def acquire(self, actor: str) -> bool:
        """
        Tenta adquirir uma chamada para o actor.
        
        Args:
            actor: Identificador do actor.
            
        Returns:
            True se adquirido, False se limit excedido.
        """
        if not self.check(actor):
            return False
        
        self._calls[actor].append(time.time())
        return True
    
    def get_remaining(self, actor: str) -> int:
        """
        Retorna número de chamadas restantes na janela atual.
        
        Args:
            actor: Identificador do actor.
            
        Returns:
            Número de chamadas restantes.
        """
        config = self._get_config(actor)
        calls = self._calls[actor]
        now = time.time()
        
        # Remove chamadas fora da janela
        window_start = now - config.window_seconds
        while calls and calls[0] < window_start:
            calls.popleft()
        
        return max(0, config.max_calls - len(calls))
    
    def get_reset_time(self, actor: str) -> float:
        """
        Retorna tempo (em segundos) até o rate limit resetar.
        
        Args:
            actor: Identificador do actor.
            
        Returns:
            Segundos até a próxima chamada ser permitida (0 se já permitido).
        """
        config = self._get_config(actor)
        calls = self._calls[actor]
        
        if len(calls) < config.max_calls:
            return 0.0
        
        # Tempo até a chamada mais antiga expirar
        now = time.time()
        oldest = calls[0] if calls else now
        return max(0.0, (oldest + config.window_seconds) - now)
    
    def reset(self, actor: str) -> None:
        """
        Reseta contador de chamadas para um actor.
        
        Args:
            actor: Identificador do actor.
        """
        self._calls[actor].clear()
        logger.debug("Rate limit reset para %s", actor)
    
    def _get_config(self, actor: str) -> RateLimitConfig:
        """Obtém config para actor, ou default se não existir."""
        return self._configs.get(actor, RateLimitConfig(
            max_calls=self._default_max_calls,
            window_seconds=self._default_window_seconds,
        ))
