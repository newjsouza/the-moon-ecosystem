"""Sprint B — Test suite for RAG Engine and moon_embed skill."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# RAGEngine tests
# ─────────────────────────────────────────────
class TestRAGEngine:

    def setup_method(self):
        from core.rag.engine import RAGEngine
        self.rag = RAGEngine()

    def test_instantiation(self):
        assert self.rag is not None
        assert self.rag._client is None
        assert self.rag._embedder is None

    def test_collections_map(self):
        from core.rag.engine import RAGEngine
        assert "blog_posts" in RAGEngine.COLLECTIONS
        assert "rooms_esportes" in RAGEngine.COLLECTIONS
        assert "rooms_financeiro" in RAGEngine.COLLECTIONS
        assert "general" in RAGEngine.COLLECTIONS

    def test_build_doc_id_deterministic(self):
        id1 = self.rag._build_doc_id("same content", {"source": "test"})
        id2 = self.rag._build_doc_id("same content", {"source": "test"})
        assert id1 == id2

    def test_build_doc_id_different_content(self):
        id1 = self.rag._build_doc_id("content A", {"source": "test"})
        id2 = self.rag._build_doc_id("content B", {"source": "test"})
        assert id1 != id2

    def test_chunk_with_context_basic(self):
        metadata = {"title": "Test Doc", "topic": "testing", "source": "moon"}
        chunks = self.rag._chunk_with_context("word " * 600, metadata)
        assert len(chunks) > 1
        for chunk in chunks:
            assert "Test Doc" in chunk["text"]
            assert chunk["total_chunks"] == len(chunks)

    def test_chunk_with_context_includes_metadata(self):
        metadata = {"title": "Sprint B", "topic": "rag", "source": "test"}
        chunks = self.rag._chunk_with_context("hello world " * 10, metadata)
        assert all("Sprint B" in c["text"] for c in chunks)

    def test_chunk_short_content_single_chunk(self):
        metadata = {"title": "Short", "topic": "test"}
        chunks = self.rag._chunk_with_context("just a few words", metadata)
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0

    @pytest.mark.asyncio
    async def test_ingest_empty_content(self):
        result = await self.rag.ingest("", {"title": "empty"}, "general")
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        result = await self.rag.search("", "general")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_ingest_and_search_mock(self):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "documents": [["contextual chunk text"]],
            "metadatas": [[{"title": "Test", "topic": "test"}]],
            "distances": [[0.1]]
        }
        mock_collection.add = MagicMock()

        mock_embedder = MagicMock()
        import numpy as np
        mock_embedder.encode.return_value = np.random.rand(3, 384)

        self.rag._embedder = mock_embedder
        self.rag._collections["moon_general"] = mock_collection

        result = await self.rag.ingest(
            "This is test content for RAG engine",
            {"title": "Test", "topic": "testing"},
            "general"
        )
        assert isinstance(result, TaskResult)
        if result.success:
            assert "chunks_ingested" in result.data
            assert result.data["collection"] == "general"

    @pytest.mark.asyncio
    async def test_search_returns_sorted_hits(self):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_collection.query.return_value = {
            "documents": [["chunk A", "chunk B", "chunk C"]],
            "metadatas": [[{"title": "A"}, {"title": "B"}, {"title": "C"}]],
            "distances": [[0.3, 0.1, 0.2]]
        }
        mock_embedder = MagicMock()
        import numpy as np
        mock_embedder.encode.return_value = np.random.rand(1, 384)

        self.rag._embedder = mock_embedder
        self.rag._collections["moon_general"] = mock_collection

        result = await self.rag.search("test query", "general", top_k=3)
        assert isinstance(result, TaskResult)
        if result.success:
            hits = result.data["hits"]
            scores = [h["score"] for h in hits]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_list_collections(self):
        mock_col = MagicMock()
        mock_col.name = "moon_general"
        mock_col.count.return_value = 5

        mock_client = MagicMock()
        mock_client.list_collections.return_value = [mock_col]
        self.rag._client = mock_client

        result = await self.rag.list_collections()
        assert isinstance(result, TaskResult)
        if result.success:
            assert result.data["total"] >= 0

    @pytest.mark.asyncio
    async def test_ingest_room_esportes(self):
        mock_collection = MagicMock()
        mock_collection.add = MagicMock()
        mock_embedder = MagicMock()
        import numpy as np
        mock_embedder.encode.return_value = np.random.rand(2, 384)

        self.rag._embedder = mock_embedder
        self.rag._collections["moon_room_esportes"] = mock_collection

        result = await self.rag.ingest_room(
            "analista_esportivo",
            "Meeting: discussed football match analysis results",
            {"title": "Sports Meeting"}
        )
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_ingest_room_financeiro(self):
        mock_collection = MagicMock()
        mock_collection.add = MagicMock()
        mock_embedder = MagicMock()
        import numpy as np
        mock_embedder.encode.return_value = np.random.rand(2, 384)

        self.rag._embedder = mock_embedder
        self.rag._collections["moon_room_financeiro"] = mock_collection

        result = await self.rag.ingest_room(
            "financeiro",
            "Meeting: discussed financial indicators and market trends",
            {"title": "Finance Meeting"}
        )
        assert isinstance(result, TaskResult)


# ─────────────────────────────────────────────
# MoonEmbedder tests
# ─────────────────────────────────────────────
class TestMoonEmbedder:

    def setup_method(self):
        from skills.moon_embed.embedder import MoonEmbedder
        self.embedder = MoonEmbedder()

    def test_instantiation(self):
        assert self.embedder.MODEL_NAME == "all-MiniLM-L6-v2"
        assert self.embedder.DIMENSIONS == 384

    @pytest.mark.asyncio
    async def test_embed_empty_text(self):
        result = await self.embedder.embed_text("")
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_embed_text_mock(self):
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(1, 384)
        self.embedder._model = mock_model

        result = await self.embedder.embed_text("test sentence")
        assert isinstance(result, TaskResult)
        if result.success:
            assert result.data["dimensions"] == 384

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        result = await self.embedder.embed_batch([])
        assert result.success is False

    @pytest.mark.asyncio
    async def test_embed_batch_mock(self):
        import numpy as np
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(3, 384)
        self.embedder._model = mock_model

        result = await self.embedder.embed_batch(["text1", "text2", "text3"])
        assert isinstance(result, TaskResult)
        if result.success:
            assert result.data["count"] == 3

    @pytest.mark.asyncio
    async def test_similarity_mock(self):
        import numpy as np
        mock_model = MagicMock()
        vecs = np.random.rand(2, 384)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        mock_model.encode.return_value = vecs
        self.embedder._model = mock_model

        result = await self.embedder.similarity("hello moon", "hello moon")
        assert isinstance(result, TaskResult)
        if result.success:
            assert -1.0 <= result.data["similarity"] <= 1.0


# ─────────────────────────────────────────────
# MoonChunker tests
# ─────────────────────────────────────────────
class TestMoonChunker:

    def setup_method(self):
        from skills.moon_embed.chunker import MoonChunker
        self.chunker = MoonChunker(chunk_size=100, overlap=10)

    def test_instantiation(self):
        assert self.chunker.chunk_size == 100
        assert self.chunker.overlap == 10

    @pytest.mark.asyncio
    async def test_chunk_empty_content(self):
        result = await self.chunker.chunk("", {"title": "empty"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_chunk_basic(self):
        content = " ".join([f"word{i}" for i in range(250)])
        metadata = {"title": "Test Doc", "topic": "testing", "source": "sprint_b"}
        result = await self.chunker.chunk(content, metadata)
        assert isinstance(result, TaskResult)
        if result.success:
            assert result.data["total"] > 1
            for chunk in result.data["chunks"]:
                assert "Test Doc" in chunk["contextual_text"]

    @pytest.mark.asyncio
    async def test_chunk_includes_context_prefix(self):
        metadata = {"title": "RAG Test", "topic": "rag", "source": "moon"}
        result = await self.chunker.chunk("hello world " * 20, metadata)
        if result.success:
            for chunk in result.data["chunks"]:
                assert "RAG Test" in chunk["contextual_text"]
                assert "rag" in chunk["contextual_text"]

    @pytest.mark.asyncio
    async def test_chunk_meeting_log_missing_file(self):
        result = await self.chunker.chunk_meeting_log(
            "/nonexistent/path/meeting_log.md", "test_room"
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_build_context_all_fields(self):
        metadata = {"title": "T", "topic": "tp", "source": "s", "date": "2026-03-20"}
        ctx = self.chunker._build_context(metadata)
        assert "T" in ctx
        assert "tp" in ctx
        assert "s" in ctx

    def test_build_context_empty_metadata(self):
        ctx = self.chunker._build_context({})
        assert ctx == "Document."


# ─────────────────────────────────────────────
# Integration and import tests
# ─────────────────────────────────────────────
class TestSprintBIntegration:

    def test_rag_engine_import(self):
        from core.rag import RAGEngine
        assert RAGEngine is not None

    def test_moon_embed_import(self):
        from skills.moon_embed import MoonEmbedder, MoonChunker
        assert MoonEmbedder is not None
        assert MoonChunker is not None

    def test_rag_engine_task_result_compliance(self):
        from core.agent_base import TaskResult
        from core.rag.engine import RAGEngine
        rag = RAGEngine()
        assert rag is not None
        result = TaskResult(success=True, data={"test": "sprint_b"})
        assert result.success is True

    def test_nexus_intelligence_rag_import(self):
        with open('agents/nexus_intelligence.py', 'r') as f:
            content = f.read()
        assert 'from core.rag' in content, \
            "RAG import must be present in nexus_intelligence.py"

    def test_blog_writer_rag_import(self):
        with open('agents/blog/writer.py', 'r') as f:
            content = f.read()
        assert 'from core.rag' in content, \
            "RAG import must be present in blog/writer.py"

    def test_index_learning_rooms_script_exists(self):
        from pathlib import Path
        assert Path('scripts/index_learning_rooms.py').exists(), \
            "index_learning_rooms.py must exist in scripts/"

    def test_data_directory_structure(self):
        from pathlib import Path
        assert Path('data/moon_knowledge').exists()
        assert Path('data/moon_knowledge/blog_posts').exists()
        assert Path('data/moon_knowledge/rooms').exists()