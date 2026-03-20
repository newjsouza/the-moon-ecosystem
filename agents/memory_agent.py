"""
agents/memory_agent.py
MemoryAgent — Favo de Memória da Colmeia.
Armazenamento e recuperação semântica via RAG local com sentence-transformers + Supabase pgvector.
Custo Zero: embeddings locais (sem API key), persistência no Supabase.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

from core.agent_base import AgentBase, TaskResult
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)


class MemoryAgent(AgentBase):
    """
    Favo de Memória da Colmeia.
    Armazena e recupera memórias semânticas usando embeddings locais
    e persistência no Supabase pgvector.
    """

    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384
    DEFAULT_SIMILARITY_THRESHOLD = 0.3

    def __init__(self):
        super().__init__()
        self.name = "MemoryAgent"
        self.description = "Memória semântica RAG com sentence-transformers + Supabase pgvector"
        self._bus = MessageBus()
        self._model: Optional[SentenceTransformer] = None
        self._supabase: Optional[Client] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Inicializa o modelo de embeddings e conexão com Supabase."""
        await super().initialize()

        # Carregar modelo de embeddings (lazy loading)
        logger.info("Carregando modelo de embeddings '%s'...", self.EMBEDDING_MODEL)
        self._model = SentenceTransformer(self.EMBEDDING_MODEL)
        logger.info("Modelo carregado — dimensão %d", self.EMBEDDING_DIM)

        # Inicializar cliente Supabase
        self._init_supabase()

        self._initialized = True
        logger.info("MemoryAgent inicializado")

    def _init_supabase(self) -> None:
        """Inicializa cliente Supabase a partir de variáveis de ambiente."""
        import os
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")

        if not supabase_url or not supabase_key:
            logger.warning(
                "SUPABASE_URL ou SUPABASE_ANON_KEY não configurados. "
                "MemoryAgent operará em modo degradado (sem persistência)."
            )
            self._supabase = None
        else:
            try:
                self._supabase = create_client(supabase_url, supabase_key)
                logger.info("Conectado ao Supabase: %s", supabase_url)
            except Exception as e:
                logger.error("Erro ao conectar ao Supabase: %s", e)
                self._supabase = None

    def _embed(self, text: str) -> List[float]:
        """Gera embedding vetorial para um texto."""
        if self._model is None:
            raise RuntimeError("Modelo de embeddings não inicializado")
        embedding = self._model.encode(text, convert_to_numpy=True)
        # Handle both numpy array and list returns
        if hasattr(embedding, 'tolist'):
            return embedding.tolist()
        return list(embedding)

    async def store(
        self,
        content: str,
        topic: str,
        agent_source: str = "MemoryAgent",
        metadata: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """
        Armazena uma memória no Supabase.

        Args:
            content: Conteúdo textual da memória
            topic: Tópico/categoria da memória
            agent_source: Agente que originou a memória
            metadata: Metadados adicionais (JSON)

        Returns:
            TaskResult com ID da memória armazenada
        """
        start = time.time()
        try:
            if not self._supabase:
                return TaskResult(
                    success=False,
                    error="Supabase não configurado — memória não persistida",
                    execution_time=time.time() - start
                )

            # Gerar embedding
            embedding = self._embed(content)

            # Inserir no banco
            result = self._supabase.table("moon_memory").insert({
                "content": content,
                "topic": topic,
                "agent_source": agent_source,
                "embedding": embedding,
                "metadata": metadata or {}
            }).execute()

            memory_id = result.data[0]["id"] if result.data else None
            logger.info("Memória armazenada: id=%s, topic=%s", memory_id, topic)

            return TaskResult(
                success=True,
                data={"id": memory_id, "topic": topic},
                execution_time=time.time() - start
            )

        except Exception as e:
            logger.exception("Erro ao armazenar memória")
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )

    async def query(
        self,
        query_text: str,
        topic: Optional[str] = None,
        match_count: int = 5,
        min_similarity: float = 0.3
    ) -> TaskResult:
        """
        Busca memórias semanticamente similares.

        Args:
            query_text: Texto de busca
            topic: Filtro por tópico (opcional)
            match_count: Número máximo de resultados
            min_similarity: Limiar mínimo de similaridade

        Returns:
            TaskResult com lista de memórias encontradas
        """
        start = time.time()
        try:
            if not self._supabase:
                return TaskResult(
                    success=False,
                    error="Supabase não configurado — busca não disponível",
                    execution_time=time.time() - start
                )

            # Gerar embedding da query
            query_embedding = self._embed(query_text)

            # Chamar função RPC de busca semântica
            result = self._supabase.rpc(
                "moon_memory_search",
                {
                    "query_embedding": query_embedding,
                    "match_count": match_count,
                    "filter_topic": topic,
                    "min_similarity": min_similarity
                }
            ).execute()

            memories = result.data or []
            logger.info("Busca retornou %d memórias", len(memories))

            return TaskResult(
                success=True,
                data={"memories": memories, "count": len(memories)},
                execution_time=time.time() - start
            )

        except Exception as e:
            logger.exception("Erro ao buscar memórias")
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )

    async def delete(self, memory_id: int) -> TaskResult:
        """Remove uma memória pelo ID."""
        start = time.time()
        try:
            if not self._supabase:
                return TaskResult(
                    success=False,
                    error="Supabase não configurado",
                    execution_time=time.time() - start
                )

            result = self._supabase.table("moon_memory").delete().eq("id", memory_id).execute()

            logger.info("Memória %s removida", memory_id)
            return TaskResult(
                success=True,
                data={"deleted_id": memory_id},
                execution_time=time.time() - start
            )

        except Exception as e:
            logger.exception("Erro ao remover memória")
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )

    async def list_by_topic(self, topic: str) -> TaskResult:
        """Lista todas as memórias de um tópico."""
        start = time.time()
        try:
            if not self._supabase:
                return TaskResult(
                    success=False,
                    error="Supabase não configurado",
                    execution_time=time.time() - start
                )

            result = self._supabase.table("moon_memory").select("*").eq("topic", topic).execute()

            memories = result.data or []
            return TaskResult(
                success=True,
                data={"memories": memories, "count": len(memories)},
                execution_time=time.time() - start
            )

        except Exception as e:
            logger.exception("Erro ao listar memórias por tópico")
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )

    async def _execute(self, task: str, **kwargs: Any) -> TaskResult:
        """Executa tarefas de gerenciamento de memória."""
        start = time.time()

        if not self._initialized:
            await self.initialize()

        try:
            if task == "store":
                content = kwargs.get("content")
                topic = kwargs.get("topic", "general")
                agent_source = kwargs.get("agent_source", "MemoryAgent")
                metadata = kwargs.get("metadata")

                if not content:
                    return TaskResult(
                        success=False,
                        error="store requer 'content'",
                        execution_time=time.time() - start
                    )

                return await self.store(content, topic, agent_source, metadata)

            elif task == "query":
                query_text = kwargs.get("query")
                topic = kwargs.get("topic")
                match_count = kwargs.get("match_count", 5)
                min_similarity = kwargs.get("min_similarity", self.DEFAULT_SIMILARITY_THRESHOLD)

                if not query_text:
                    return TaskResult(
                        success=False,
                        error="query requer 'query'",
                        execution_time=time.time() - start
                    )

                return await self.query(query_text, topic, match_count, min_similarity)

            elif task == "delete":
                memory_id = kwargs.get("memory_id")
                if not memory_id:
                    return TaskResult(
                        success=False,
                        error="delete requer 'memory_id'",
                        execution_time=time.time() - start
                    )
                return await self.delete(memory_id)

            elif task == "list_by_topic":
                topic = kwargs.get("topic")
                if not topic:
                    return TaskResult(
                        success=False,
                        error="list_by_topic requer 'topic'",
                        execution_time=time.time() - start
                    )
                return await self.list_by_topic(topic)

            elif task == "health":
                return TaskResult(
                    success=True,
                    data={
                        "model_loaded": self._model is not None,
                        "supabase_connected": self._supabase is not None,
                        "embedding_dim": self.EMBEDDING_DIM
                    },
                    execution_time=time.time() - start
                )

            else:
                return TaskResult(
                    success=False,
                    error=f"Task desconhecida: {task}",
                    execution_time=time.time() - start
                )

        except Exception as e:
            logger.exception("MemoryAgent._execute falhou")
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )

    async def _on_memory_store(self, message: Any) -> None:
        """Handler para tópico memory.store."""
        payload = getattr(message, "payload", {})
        event = payload.get("event")

        if event == "sync":
            logger.info("Memory sync solicitado via message bus")
            # Pode implementar lógica de sincronização aqui

    def start_listening(self) -> None:
        """Inicia escuta dos tópicos do message bus."""
        self._bus.subscribe("memory.store", self._on_memory_store)
        logger.info("MemoryAgent ouvindo tópico memory.store")
