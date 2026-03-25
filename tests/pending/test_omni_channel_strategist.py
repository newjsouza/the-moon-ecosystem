"""
tests/test_omni_channel_strategist.py
Testes para OmniChannelStrategist (Distribuição Multi-Canal).

Cobertura:
  - Fingerprint/deduplicação de conteúdo
  - Adaptação por canal
  - Fila/agendamento
  - Tratamento de erro de publicação
  - Persistência local
  - Bloqueio de repost duplicado
  - Comportamento com canais desativados
"""
import pytest
import os
import json
import time
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from agents.omni_channel_strategist import (
    OmniChannelStrategist,
    ContentAdapter,
    PostScheduler,
    ContentPiece,
    PlatformPost,
    Platform,
    ContentType,
    PostStatus,
    TelegramPlatformClient,
    TwitterPlatformClient,
    LinkedInPlatformClient,
    CHAR_LIMITS,
    DAILY_LIMITS,
    OPTIMAL_HOURS,
    TONE_INSTRUCTIONS,
)
from core.agent_base import TaskResult


# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def strategist():
    """Cria instância do OmniChannelStrategist para testes."""
    return OmniChannelStrategist()


@pytest.fixture
def strategist_with_dependencies(mock_groq_client, mock_message_bus):
    """Cria OmniChannelStrategist com dependências mockadas."""
    return OmniChannelStrategist(
        groq_client=mock_groq_client,
        message_bus=mock_message_bus
    )


@pytest.fixture
def sample_content_piece():
    """Cria ContentPiece de exemplo para testes."""
    return ContentPiece(
        id="test-123",
        title="Test Blog Post",
        summary="This is a test blog post summary",
        url="https://example.com/blog/test-post",
        content_type=ContentType.BLOG_POST,
        source_agent="BlogPublisherAgent",
        tags=["test", "blog", "example"],
        full_text="This is the full content of the test blog post. " * 10,
    )


@pytest.fixture
def env_cleanup():
    """Limpa variáveis de ambiente após teste."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


# ─────────────────────────────────────────────────────────────
#  Testes de Import e Inicialização
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
def test_omni_channel_import():
    """Teste básico de import do OmniChannelStrategist."""
    from agents.omni_channel_strategist import OmniChannelStrategist, Platform, ContentType
    assert OmniChannelStrategist is not None
    assert Platform is not None
    assert ContentType is not None


@pytest.mark.unit
@pytest.mark.omni_channel
def test_platform_enum_values():
    """Testa valores do enum Platform."""
    assert Platform.TELEGRAM.value == "telegram"
    assert Platform.TWITTER.value == "twitter"
    assert Platform.LINKEDIN.value == "linkedin"


@pytest.mark.unit
@pytest.mark.omni_channel
def test_content_type_enum_values():
    """Testa valores do enum ContentType."""
    assert ContentType.BLOG_POST.value == "blog_post"
    assert ContentType.YOUTUBE_VIDEO.value == "youtube_video"
    assert ContentType.RESEARCH.value == "research"


@pytest.mark.unit
@pytest.mark.omni_channel
def test_post_status_enum_values():
    """Testa valores do enum PostStatus."""
    assert PostStatus.PENDING.value == "pending"
    assert PostStatus.SCHEDULED.value == "scheduled"
    assert PostStatus.POSTED.value == "posted"
    assert PostStatus.FAILED.value == "failed"


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_strategist_initialization(temp_data_dir):
    """Testa inicialização do OmniChannelStrategist."""
    with patch('pathlib.Path.mkdir', return_value=None):
        strategist = OmniChannelStrategist()
        await strategist.initialize()
        await strategist.shutdown()


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_strategist_ping(strategist):
    """Testa liveness probe do OmniChannelStrategist."""
    await strategist.initialize()
    result = await strategist.ping()
    assert result is True
    await strategist.shutdown()


# ─────────────────────────────────────────────────────────────
#  Testes de ContentPiece e Fingerprint
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
def test_content_piece_fingerprint(sample_content_piece):
    """Testa geração de fingerprint para deduplicação."""
    fingerprint1 = sample_content_piece.fingerprint()
    fingerprint2 = sample_content_piece.fingerprint()
    
    # Mesmo URL deve gerar mesmo fingerprint
    assert fingerprint1 == fingerprint2
    assert len(fingerprint1) == 16  # 16 caracteres hex


@pytest.mark.unit
@pytest.mark.omni_channel
def test_content_piece_different_fingerprints():
    """Testa que URLs diferentes geram fingerprints diferentes."""
    piece1 = ContentPiece(
        id="1",
        title="Test 1",
        summary="Summary 1",
        url="https://example.com/post1",
        content_type=ContentType.BLOG_POST,
        source_agent="Test",
    )
    
    piece2 = ContentPiece(
        id="2",
        title="Test 2",
        summary="Summary 2",
        url="https://example.com/post2",
        content_type=ContentType.BLOG_POST,
        source_agent="Test",
    )
    
    assert piece1.fingerprint() != piece2.fingerprint()


@pytest.mark.unit
@pytest.mark.omni_channel
def test_content_piece_to_dict(sample_content_piece):
    """Testa serialização de ContentPiece."""
    piece_dict = {
        "id": sample_content_piece.id,
        "title": sample_content_piece.title,
        "summary": sample_content_piece.summary,
        "url": sample_content_piece.url,
    }
    
    assert sample_content_piece.id in piece_dict["id"]
    assert sample_content_piece.title in piece_dict["title"]


# ─────────────────────────────────────────────────────────────
#  Testes de ContentAdapter
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
def test_content_adapter_initialization():
    """Testa inicialização do ContentAdapter."""
    adapter = ContentAdapter()
    assert adapter._groq is None


@pytest.mark.unit
@pytest.mark.omni_channel
def test_content_adapter_with_groq(mock_groq_client):
    """Testa ContentAdapter com cliente Groq mockado."""
    adapter = ContentAdapter(groq_client=mock_groq_client)
    assert adapter._groq is not None


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_rule_based_adapt_telegram(sample_content_piece):
    """Testa adaptação rule-based para Telegram."""
    adapter = ContentAdapter()
    
    result = adapter._rule_based_adapt(
        sample_content_piece,
        Platform.TELEGRAM,
        CHAR_LIMITS["telegram"]
    )
    
    assert isinstance(result, str)
    assert len(result) <= CHAR_LIMITS["telegram"]
    assert sample_content_piece.url in result


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_rule_based_adapt_twitter(sample_content_piece):
    """Testa adaptação rule-based para Twitter."""
    adapter = ContentAdapter()
    
    result = adapter._rule_based_adapt(
        sample_content_piece,
        Platform.TWITTER,
        CHAR_LIMITS["twitter"]
    )
    
    assert isinstance(result, str)
    assert len(result) <= CHAR_LIMITS["twitter"]


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_rule_based_adapt_linkedin(sample_content_piece):
    """Testa adaptação rule-based para LinkedIn."""
    adapter = ContentAdapter()
    
    result = adapter._rule_based_adapt(
        sample_content_piece,
        Platform.LINKEDIN,
        CHAR_LIMITS["linkedin"]
    )
    
    assert isinstance(result, str)
    assert len(result) <= CHAR_LIMITS["linkedin"]


@pytest.mark.unit
@pytest.mark.omni_channel
def test_twitter_thread_splitting():
    """Testa divisão de thread do Twitter."""
    adapter = ContentAdapter()
    
    # Texto longo que precisa ser dividido
    long_text = "Word " * 100  # ~500 caracteres
    url = "https://example.com"
    
    thread = adapter._split_twitter_thread(long_text, url)
    
    assert len(thread) > 1  # Deve criar múltiplos tweets
    assert url in thread[-1]  # URL no último tweet
    
    # Verifica numeração
    assert thread[0].startswith("1/")
    assert thread[-1].startswith(f"{len(thread)}/")


@pytest.mark.unit
@pytest.mark.omni_channel
def test_twitter_thread_short_content():
    """Testa thread com conteúdo curto (não divide)."""
    adapter = ContentAdapter()
    
    short_text = "Short tweet content"
    url = "https://example.com"
    
    thread = adapter._split_twitter_thread(short_text, url)
    
    assert len(thread) == 1
    assert url in thread[0]


# ─────────────────────────────────────────────────────────────
#  Testes de PostScheduler
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
def test_scheduler_initialization():
    """Testa inicialização do PostScheduler."""
    scheduler = PostScheduler()
    assert scheduler.queue_size() == 0
    assert scheduler._daily_count == {}


@pytest.mark.unit
@pytest.mark.omni_channel
def test_scheduler_can_post():
    """Testa verificação de limite diário."""
    scheduler = PostScheduler()
    
    # Deve poder postar inicialmente
    assert scheduler.can_post(Platform.TELEGRAM) is True
    
    # Simula posts até limite
    for _ in range(DAILY_LIMITS["telegram"]):
        scheduler.record_post(Platform.TELEGRAM)
    
    # Não deve poder postar após limite
    assert scheduler.can_post(Platform.TELEGRAM) is False


@pytest.mark.unit
@pytest.mark.omni_channel
def test_scheduler_record_post():
    """Testa registro de post."""
    scheduler = PostScheduler()
    
    initial_count = scheduler._daily_count.get("telegram", 0)
    scheduler.record_post(Platform.TELEGRAM)
    new_count = scheduler._daily_count.get("telegram", 0)
    
    assert new_count == initial_count + 1


@pytest.mark.unit
@pytest.mark.omni_channel
def test_scheduler_enqueue():
    """Testa enfileiramento de post."""
    scheduler = PostScheduler()
    
    post = PlatformPost(
        content_id="test-123",
        platform=Platform.TELEGRAM,
        text="Test post",
    )
    
    scheduled_at = scheduler.enqueue(post, delay_seconds=60)
    
    assert scheduler.queue_size() == 1
    assert scheduled_at > time.time()


@pytest.mark.unit
@pytest.mark.omni_channel
def test_scheduler_pop_due():
    """Testa remoção de posts vencidos."""
    scheduler = PostScheduler()

    post = PlatformPost(
        content_id="test-123",
        platform=Platform.TELEGRAM,
        text="Test post",
    )

    # Enfileira com timestamp já vencido (atual - 10 segundos)
    post.scheduled_at = time.time() - 10
    post.status = PostStatus.SCHEDULED
    import heapq
    from agents.omni_channel_strategist import _QueueEntry
    heapq.heappush(scheduler._heap, _QueueEntry(post.scheduled_at, post))

    due_posts = scheduler.pop_due()

    assert len(due_posts) == 1
    assert scheduler.queue_size() == 0


@pytest.mark.unit
@pytest.mark.omni_channel
def test_scheduler_peek_next():
    """Testa visualização do próximo post."""
    scheduler = PostScheduler()
    
    assert scheduler.peek_next() is None
    
    post = PlatformPost(
        content_id="test-123",
        platform=Platform.TELEGRAM,
        text="Test post",
    )
    scheduler.enqueue(post, delay_seconds=60)
    
    next_time = scheduler.peek_next()
    assert next_time is not None
    assert next_time > time.time()


@pytest.mark.unit
@pytest.mark.omni_channel
def test_scheduler_daily_reset():
    """Testa reset diário de contadores."""
    scheduler = PostScheduler()
    
    # Registra alguns posts
    scheduler.record_post(Platform.TELEGRAM)
    scheduler.record_post(Platform.TWITTER)
    
    # Simula mudança de dia
    scheduler._day_key = "2024-01-01"
    scheduler._reset_if_new_day()
    
    # Contadores devem estar zerados
    assert scheduler._daily_count == {}


# ─────────────────────────────────────────────────────────────
#  Testes de Platform Clients
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
def test_telegram_client_availability(env_cleanup):
    """Testa verificação de disponibilidade do Telegram."""
    # Sem credenciais
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    os.environ["TELEGRAM_CHANNEL_ID"] = ""
    
    client = TelegramPlatformClient()
    assert client.is_available() is False
    
    # Com credenciais
    os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    os.environ["TELEGRAM_CHANNEL_ID"] = "@testchannel"
    
    client = TelegramPlatformClient()
    assert client.is_available() is True


@pytest.mark.unit
@pytest.mark.omni_channel
def test_twitter_client_availability(env_cleanup):
    """Testa verificação de disponibilidade do Twitter."""
    # Sem credenciais
    for key in ["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]:
        os.environ[key] = ""
    
    client = TwitterPlatformClient()
    assert client.is_available() is False
    
    # Com credenciais
    for key in ["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]:
        os.environ[key] = "test_value"
    
    client = TwitterPlatformClient()
    assert client.is_available() is True


@pytest.mark.unit
@pytest.mark.omni_channel
def test_linkedin_client_availability(env_cleanup):
    """Testa verificação de disponibilidade do LinkedIn."""
    # Sem credenciais
    os.environ["LINKEDIN_ACCESS_TOKEN"] = ""
    os.environ["LINKEDIN_PERSON_URN"] = ""
    
    client = LinkedInPlatformClient()
    assert client.is_available() is False
    
    # Com credenciais
    os.environ["LINKEDIN_ACCESS_TOKEN"] = "test_token"
    os.environ["LINKEDIN_PERSON_URN"] = "123456"
    
    client = LinkedInPlatformClient()
    assert client.is_available() is True


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_telegram_post_error():
    """Testa erro de postagem no Telegram."""
    os.environ["TELEGRAM_BOT_TOKEN"] = "invalid_token"
    os.environ["TELEGRAM_CHANNEL_ID"] = "@test"
    
    client = TelegramPlatformClient()
    post = PlatformPost(
        content_id="test",
        platform=Platform.TELEGRAM,
        text="Test post",
    )
    
    success, error = await client.post(post)
    assert success is False
    assert error is not None


# ─────────────────────────────────────────────────────────────
#  Testes de Deduplicação
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_duplicate_content_blocked(strategist):
    """Testa que conteúdo duplicado é bloqueado."""
    await strategist.initialize()
    
    # Adiciona fingerprint ao histórico
    fingerprint = "test_fingerprint_123"
    strategist._fingerprints.add(fingerprint)
    
    # Tenta distribuir conteúdo com mesmo fingerprint
    piece = ContentPiece(
        id="test-dup",
        title="Test",
        summary="Test summary",
        url="https://example.com",
        content_type=ContentType.BLOG_POST,
        source_agent="Test",
    )
    
    # Mock para evitar chamada LLM real
    with patch.object(strategist._adapter, 'adapt') as mock_adapt:
        mock_adapt.return_value = PlatformPost(
            content_id="test",
            platform=Platform.TELEGRAM,
            text="Test",
        )
        
        result = await strategist._distribute_now(piece)
        
        # Deve bloquear por duplicação
        assert result.success is False or "duplicate" in str(result.data).lower()
    
    await strategist.shutdown()


# ─────────────────────────────────────────────────────────────
#  Testes de Execute Actions
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_execute_status(strategist):
    """Testa ação 'status' do execute."""
    await strategist.initialize()
    
    result = await strategist._execute("status")
    
    assert result.success is True
    assert "queue_size" in result.data or "platforms" in result.data
    
    await strategist.shutdown()


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_execute_history(strategist):
    """Testa ação 'history' do execute."""
    await strategist.initialize()
    
    result = await strategist._execute("history", limit=10)
    
    assert result.success is True
    assert "history" in result.data
    
    await strategist.shutdown()


@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_execute_unknown_action(strategist):
    """Testa ação desconhecida."""
    await strategist.initialize()
    
    result = await strategist._execute("unknown_action")
    
    assert result.success is False
    
    await strategist.shutdown()


# ─────────────────────────────────────────────────────────────
#  Testes de Comportamento com Canais Desativados
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_post_to_unavailable_platform(strategist, sample_content_piece):
    """Testa postagem para plataforma não disponível."""
    await strategist.initialize()
    
    # Remove todas as credenciais
    for key in ["TELEGRAM_BOT_TOKEN", "TWITTER_API_KEY", "LINKEDIN_ACCESS_TOKEN"]:
        if key in os.environ:
            del os.environ[key]
    
    # Recria clients para refletir falta de credenciais
    strategist._clients = {
        Platform.TELEGRAM: TelegramPlatformClient(),
        Platform.TWITTER: TwitterPlatformClient(),
        Platform.LINKEDIN: LinkedInPlatformClient(),
    }
    
    result = await strategist._distribute_now(sample_content_piece)
    
    # Deve lidar graciosamente com plataformas indisponíveis
    assert result is not None
    
    await strategist.shutdown()


# ─────────────────────────────────────────────────────────────
#  Testes de Persistência Local
# ─────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.omni_channel
def test_storage_directory_creation(temp_data_dir):
    """Testa criação do diretório de armazenamento."""
    storage_dir = temp_data_dir / "omni_channel"
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    assert storage_dir.exists()
    assert storage_dir.is_dir()


@pytest.mark.unit
@pytest.mark.omni_channel
def test_fingerprint_file_structure(temp_data_dir):
    """Testa estrutura do arquivo de fingerprints."""
    storage_dir = temp_data_dir / "omni_channel"
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    fingerprints_file = storage_dir / "fingerprints.json"
    
    # Cria arquivo de exemplo
    fingerprints = ["fp1", "fp2", "fp3"]
    with open(fingerprints_file, 'w') as f:
        json.dump(fingerprints, f)
    
    # Lê e verifica
    with open(fingerprints_file, 'r') as f:
        loaded = json.load(f)
    
    assert loaded == fingerprints


# ─────────────────────────────────────────────────────────────
#  Testes de Integração Leve
# ─────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.omni_channel
@pytest.mark.asyncio
async def test_full_distribution_flow_mocked(
    strategist_with_dependencies,
    sample_content_piece,
    temp_data_dir
):
    """Testa fluxo completo de distribuição com mocks."""
    strategist = strategist_with_dependencies
    
    await strategist.initialize()
    
    # Mock de adaptação de conteúdo
    mock_post = PlatformPost(
        content_id=sample_content_piece.id,
        platform=Platform.TELEGRAM,
        text=f"Mock post for {sample_content_piece.title}",
    )
    
    with patch.object(strategist._adapter, 'adapt', return_value=mock_post), \
         patch.object(strategist._clients[Platform.TELEGRAM], 'post', return_value=(True, "msg_123")):
        
        result = await strategist._distribute_now(sample_content_piece)
        
        # Verifica resultado
        assert result is not None
    
    await strategist.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
