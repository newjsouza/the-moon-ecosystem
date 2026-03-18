import time
import pytest
from core.session_manager import SessionManager, get_session_manager
from core.orchestrator import Orchestrator


def test_create_session():
    """Testa criação e recuperação de sessão."""
    sm = SessionManager()
    session_id = "test_user_123"
    test_data = {"key": "value", "number": 42}
    
    sm.set_session(session_id, test_data)
    retrieved = sm.get_session(session_id)
    
    assert retrieved == test_data


def test_session_scope_user():
    """Testa que o modo user gera IDs únicos por usuário."""
    sm = SessionManager()
    
    session_id_1 = sm.build_session_id("user", "user123")
    session_id_2 = sm.build_session_id("user", "user456")
    
    assert session_id_1 == "user:user123"
    assert session_id_2 == "user:user456"
    assert session_id_1 != session_id_2


def test_session_scope_channel():
    """Testa que o modo channel gera IDs únicos por canal."""
    sm = SessionManager()
    
    session_id_1 = sm.build_session_id("channel", channel="chan123")
    session_id_2 = sm.build_session_id("channel", channel="chan456")
    
    assert session_id_1 == "channel:chan123"
    assert session_id_2 == "channel:chan456"
    assert session_id_1 != session_id_2


def test_session_scope_workspace():
    """Testa que o modo workspace gera IDs únicos por workspace."""
    sm = SessionManager()
    
    session_id_1 = sm.build_session_id("workspace", workspace="ws123")
    session_id_2 = sm.build_session_id("workspace", workspace="ws456")
    
    assert session_id_1 == "workspace:ws123"
    assert session_id_2 == "workspace:ws456"
    assert session_id_1 != session_id_2


def test_session_ttl_expiry():
    """Testa expiração de sessão após TTL."""
    sm = SessionManager(default_ttl=1)  # 1 segundo de TTL
    
    session_id = "expiring_session"
    test_data = {"data": "will_expire"}
    
    sm.set_session(session_id, test_data)
    retrieved_before = sm.get_session(session_id)
    assert retrieved_before == test_data
    
    # Esperar mais tempo que o TTL
    time.sleep(1.1)
    
    retrieved_after = sm.get_session(session_id)
    assert retrieved_after == {}  # Deve estar vazio pois expirou


def test_clear_expired():
    """Testa remoção de sessões expiradas."""
    sm = SessionManager(default_ttl=1)
    
    # Criar duas sessões: uma expirando e outra não
    sm.set_session("expiring_1", {"data": "exp1"})
    sm.set_session("expiring_2", {"data": "exp2"})
    
    # Esperar para expirar
    time.sleep(1.1)
    
    # Criar uma sessão que não vai expirar
    sm.set_session("valid", {"data": "valid"}, )
    # Precisamos passar um TTL maior explicitamente
    sm.set_session("long_lived", {"_ttl": 10, "data": "long"})
    
    cleared_count = sm.clear_expired()
    assert cleared_count == 2  # As duas primeiras deveriam ter sido removidas
    
    # Validar que as não expiradas ainda existem
    assert sm.get_session("long_lived")["data"] == "long"
    
    # Validar que as expiradas não existem mais
    assert sm.get_session("expiring_1") == {}
    assert sm.get_session("expiring_2") == {}


def test_get_stats():
    """Testa obtenção de estatísticas."""
    sm = SessionManager(default_ttl=10)
    
    # Criar algumas sessões de diferentes modos
    sm.set_session("user:user1", {"data": "user"})
    sm.set_session("channel:chan1", {"data": "channel"})
    sm.set_session("workspace:ws1", {"data": "workspace"})
    sm.set_session("global:default", {"data": "global"})
    
    stats = sm.get_stats()
    
    # Apenas verificar o total, pois o modo está embutido no ID e não armazenado nos dados
    assert stats["total"] == 4
    assert stats["expired"] == 0


def test_singleton():
    """Testa que get_session_manager retorna a mesma instância."""
    sm1 = get_session_manager()
    sm2 = get_session_manager()
    
    assert sm1 is sm2
    assert isinstance(sm1, SessionManager)
    assert isinstance(sm2, SessionManager)


def test_orchestrator_get_session_context():
    """Testa integração do SessionManager com o Orchestrator."""
    orch = Orchestrator()
    sm = orch.session_manager
    
    # Testar contexto de usuário
    user_data = {"context": "user_specific", "page": 3}
    orch._set_session_context(user_data, user_id="user123", mode="user")
    
    retrieved = orch._get_session_context(user_id="user123", mode="user")
    assert retrieved == user_data
    
    # Testar contexto de canal
    channel_data = {"context": "channel_specific", "filter": "important"}
    orch._set_session_context(channel_data, channel="telegram", mode="channel")
    
    retrieved = orch._get_session_context(channel="telegram", mode="channel")
    assert retrieved == channel_data
    
    # Verificar que os contextos são diferentes
    user_retrieved = orch._get_session_context(user_id="user123", mode="user")
    channel_retrieved = orch._get_session_context(channel="telegram", mode="channel")
    
    assert user_retrieved != channel_retrieved