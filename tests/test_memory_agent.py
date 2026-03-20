"""
tests/test_memory_agent.py
Tests for MemoryAgent — Favo de Memória da Colmeia.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from agents.memory_agent import MemoryAgent
from core.agent_base import AgentPriority, TaskResult


@pytest.fixture
def mock_model():
    """Mock do modelo de embeddings."""
    model = MagicMock()
    model.encode.return_value = [0.1] * 384  # Lista simples, não numpy
    return model


@pytest.fixture
def mock_supabase():
    """Mock do cliente Supabase."""
    client = MagicMock()
    
    # Configurar chain de métodos para insert (usando MagicMock, não AsyncMock)
    insert_result = MagicMock()
    insert_result.data = [{"id": 123}]
    insert_mock = MagicMock()
    insert_mock.execute = MagicMock(return_value=insert_result)
    client.table.return_value.insert.return_value = insert_mock
    
    # Configurar chain para select
    select_result = MagicMock()
    select_result.data = [{"id": 1, "content": "test"}]
    select_mock = MagicMock()
    select_mock.eq.return_value = select_mock
    select_mock.execute = MagicMock(return_value=select_result)
    client.table.return_value.select.return_value = select_mock
    
    # Configurar chain para delete
    delete_result = MagicMock()
    delete_result.data = []
    delete_mock = MagicMock()
    delete_mock.eq.return_value = delete_mock
    delete_mock.execute = MagicMock(return_value=delete_result)
    client.table.return_value.delete.return_value = delete_mock
    
    # Configurar rpc para busca semântica
    rpc_result = MagicMock()
    rpc_result.data = [{"id": 1, "similarity": 0.85}]
    rpc_mock = MagicMock()
    rpc_mock.execute = MagicMock(return_value=rpc_result)
    client.rpc.return_value = rpc_mock
    
    return client


class TestMemoryAgentInstantiation:
    """Testes de instanciação e inicialização."""

    def test_memory_agent_instantiation(self):
        """Testa que o MemoryAgent é instanciado corretamente."""
        agent = MemoryAgent()
        assert agent.name == "MemoryAgent"
        assert agent.priority == AgentPriority.MEDIUM
        assert agent._model is None
        assert agent._supabase is None

    @pytest.mark.asyncio
    async def test_initialize_loads_model(self, mock_model):
        """Testa que initialize() carrega o modelo."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch.dict('os.environ', {}, clear=True):  # Sem vars do Supabase
            agent = MemoryAgent()
            await agent.initialize()
            
            assert agent._initialized is True
            assert agent._model is not None
            assert agent._supabase is None  # Sem vars de ambiente

    @pytest.mark.asyncio
    async def test_initialize_with_supabase(self, mock_model, mock_supabase):
        """Testa initialize com Supabase configurado."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase), \
             patch.dict('os.environ', {
                 'SUPABASE_URL': 'http://localhost:54321',
                 'SUPABASE_ANON_KEY': 'test-key'
             }):
            agent = MemoryAgent()
            await agent.initialize()
            
            assert agent._initialized is True
            assert agent._model is not None
            assert agent._supabase is not None


class TestMemoryAgentEmbed:
    """Testes de geração de embedding."""

    @pytest.mark.asyncio
    async def test_embed_generates_vector(self, mock_model):
        """Testa geração de embedding."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model):
            agent = MemoryAgent()
            agent._model = mock_model
            
            embedding = agent._embed("test text")
            assert isinstance(embedding, list)
            assert len(embedding) == 384

    @pytest.mark.asyncio
    async def test_embed_without_model(self):
        """Testa que _embed falha sem modelo."""
        agent = MemoryAgent()
        agent._model = None
        
        with pytest.raises(RuntimeError, match="Modelo de embeddings não inicializado"):
            agent._embed("test")


class TestMemoryAgentStore:
    """Testes de armazenamento de memórias."""

    @pytest.mark.asyncio
    async def test_store_success(self, mock_model, mock_supabase):
        """Testa armazenamento de memória com sucesso."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            
            result = await agent.store(
                content="Test memory content",
                topic="test_topic",
                agent_source="TestAgent",
                metadata={"key": "value"}
            )
            
            assert result.success is True
            assert result.data["id"] == 123
            assert result.data["topic"] == "test_topic"

    @pytest.mark.asyncio
    async def test_store_without_supabase(self, mock_model):
        """Testa store sem Supabase configurado."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = None
            
            result = await agent.store(content="test", topic="test")
            
            assert result.success is False
            assert "Supabase não configurado" in result.error


class TestMemoryAgentQuery:
    """Testes de busca semântica."""

    @pytest.mark.asyncio
    async def test_query_success(self, mock_model, mock_supabase):
        """Testa busca semântica com sucesso."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            
            result = await agent.query(
                query_text="test query",
                topic="test_topic",
                match_count=5,
                min_similarity=0.3
            )
            
            assert result.success is True
            assert result.data["count"] >= 0
            assert "memories" in result.data

    @pytest.mark.asyncio
    async def test_query_without_supabase(self, mock_model):
        """Testa query sem Supabase configurado."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = None
            
            result = await agent.query(query_text="test")
            
            assert result.success is False
            assert "Supabase não configurado" in result.error


class TestMemoryAgentDelete:
    """Testes de remoção de memórias."""

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_model, mock_supabase):
        """Testa remoção de memória com sucesso."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            
            result = await agent.delete(memory_id=123)
            
            assert result.success is True
            assert result.data["deleted_id"] == 123


class TestMemoryAgentListByTopic:
    """Testes de listagem por tópico."""

    @pytest.mark.asyncio
    async def test_list_by_topic_success(self, mock_model, mock_supabase):
        """Testa listagem de memórias por tópico."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            
            result = await agent.list_by_topic(topic="test_topic")
            
            assert result.success is True
            assert "memories" in result.data


class TestMemoryAgentExecute:
    """Testes do método _execute."""

    @pytest.mark.asyncio
    async def test_execute_store(self, mock_model, mock_supabase):
        """Testa _execute com task 'store'."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            agent._initialized = True  # Evita chamar initialize()
            
            result = await agent._execute(
                "store",
                content="test content",
                topic="test",
                agent_source="TestAgent"
            )
            
            assert result.success is True
            assert "id" in result.data

    @pytest.mark.asyncio
    async def test_execute_query(self, mock_model, mock_supabase):
        """Testa _execute com task 'query'."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            agent._initialized = True  # Evita chamar initialize()
            
            result = await agent._execute(
                "query",
                query="test query",
                topic="test",
                match_count=3
            )
            
            assert result.success is True
            assert "memories" in result.data

    @pytest.mark.asyncio
    async def test_execute_delete(self, mock_model, mock_supabase):
        """Testa _execute com task 'delete'."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            agent._initialized = True  # Evita chamar initialize()
            
            result = await agent._execute("delete", memory_id=123)
            
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_list_by_topic(self, mock_model, mock_supabase):
        """Testa _execute com task 'list_by_topic'."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            agent._initialized = True  # Evita chamar initialize()
            
            result = await agent._execute("list_by_topic", topic="test")
            
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_health(self, mock_model, mock_supabase):
        """Testa _execute com task 'health'."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            agent._initialized = True  # Evita chamar initialize()
            
            result = await agent._execute("health")
            
            assert result.success is True
            assert "model_loaded" in result.data
            assert result.data["model_loaded"] is True
            assert result.data["embedding_dim"] == 384

    @pytest.mark.asyncio
    async def test_execute_missing_content(self, mock_model, mock_supabase):
        """Testa _execute store sem content."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            
            result = await agent._execute("store", topic="test")
            
            assert result.success is False
            assert "requer 'content'" in result.error

    @pytest.mark.asyncio
    async def test_execute_missing_query(self, mock_model, mock_supabase):
        """Testa _execute query sem query."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            
            result = await agent._execute("query", topic="test")
            
            assert result.success is False
            assert "requer 'query'" in result.error

    @pytest.mark.asyncio
    async def test_execute_unknown_task(self, mock_model, mock_supabase):
        """Testa _execute com task desconhecida."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model), \
             patch('agents.memory_agent.create_client', return_value=mock_supabase):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._supabase = mock_supabase
            
            result = await agent._execute("unknown_task")
            
            assert result.success is False
            assert "desconhecida" in result.error


class TestMemoryAgentMessageBus:
    """Testes de integração com MessageBus."""

    @pytest.mark.asyncio
    async def test_on_memory_store_sync_event(self, mock_model):
        """Testa handler de memory.store com evento sync."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model):
            agent = MemoryAgent()
            agent._model = mock_model
            
            mock_message = MagicMock()
            mock_message.payload = {"event": "sync"}
            
            # Não deve levantar exceção
            await agent._on_memory_store(mock_message)

    def test_start_listening(self, mock_model):
        """Testa início da escuta do message bus."""
        with patch('agents.memory_agent.SentenceTransformer', return_value=mock_model):
            agent = MemoryAgent()
            agent._model = mock_model
            agent._initialized = True
            
            # O subscribe é síncrono, não precisa de await
            agent._bus.subscribe = MagicMock()  # Substitui o método no objeto
            agent.start_listening()
            agent._bus.subscribe.assert_called_once_with("memory.store", agent._on_memory_store)
