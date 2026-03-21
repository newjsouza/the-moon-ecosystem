"""
RAGEngine — Retrieval-Augmented Generation core.
Sits ON TOP of MemoryAgent. Does NOT replace it.
Uses ChromaDB for local vector storage + contextual chunking.
"""
import asyncio
import logging
import hashlib
from typing import Optional
from core.agent_base import TaskResult

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Central RAG engine for The Moon ecosystem.
    Wraps MemoryAgent with contextual chunking and collection routing.
    Collections map directly to Learning Rooms and knowledge domains.
    """

    COLLECTIONS = {
        "blog_posts": "moon_blog",
        "codex": "moon_codex",
        "sessions": "moon_sessions",
        "rooms_esportes": "moon_room_esportes",
        "rooms_financeiro": "moon_room_financeiro",
        "general": "moon_general",
    }

    def __init__(self):
        self._client = None
        self._collections = {}
        self._embedder = None
        self._memory_agent = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_client(self):
        """Lazy initialization of ChromaDB client (local, zero cost)."""
        if self._client is None:
            import chromadb
            from pathlib import Path
            db_path = str(Path("data/moon_knowledge/.chromadb"))
            self._client = chromadb.PersistentClient(path=db_path)
            self.logger.info(f"ChromaDB initialized at {db_path}")
        return self._client

    def _get_embedder(self):
        """Lazy initialization of sentence-transformers embedder."""
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            self.logger.info("Embedder all-MiniLM-L6-v2 loaded ✅")
        return self._embedder

    def _get_collection(self, collection_name: str):
        """Get or create a ChromaDB collection."""
        chroma_name = self.COLLECTIONS.get(collection_name, f"moon_{collection_name}")
        if chroma_name not in self._collections:
            client = self._get_client()
            self._collections[chroma_name] = client.get_or_create_collection(
                name=chroma_name,
                metadata={"hnsw:space": "cosine"}
            )
        return self._collections[chroma_name]

    def _build_doc_id(self, content: str, metadata: dict) -> str:
        """Generate stable doc_id from content hash."""
        source = f"{metadata.get('source', '')}{content[:100]}"
        return hashlib.md5(source.encode()).hexdigest()

    def _chunk_with_context(self, content: str, metadata: dict,
                             chunk_size: int = 500, overlap: int = 50) -> list[dict]:
        """
        Contextual chunking (Anthropic pattern):
        Prepends document context to each chunk for better retrieval.
        """
        doc_context = (
            f"Document: {metadata.get('title', 'Unknown')}. "
            f"Topic: {metadata.get('topic', 'general')}. "
            f"Source: {metadata.get('source', 'moon')}. "
        )

        words = content.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            contextual_chunk = f"{doc_context}\n\n{chunk_text}"
            chunks.append({
                "text": contextual_chunk,
                "raw_text": chunk_text,
                "chunk_index": len(chunks),
                "total_chunks": None,
            })

        for chunk in chunks:
            chunk["total_chunks"] = len(chunks)

        return chunks

    async def ingest(self, content: str, metadata: dict,
                     collection: str = "general", **kwargs) -> TaskResult:
        """
        Ingest content into RAG collection with contextual chunking.
        metadata should include: title, topic, source, date (optional)
        """
        start = asyncio.get_event_loop().time()
        try:
            if not content or not content.strip():
                return TaskResult(success=False, error="Content cannot be empty")

            chunks = self._chunk_with_context(content, metadata)
            embedder = self._get_embedder()
            col = self._get_collection(collection)

            doc_id_base = self._build_doc_id(content, metadata)
            texts = [c["text"] for c in chunks]
            embeddings = embedder.encode(texts).tolist()

            ids = [f"{doc_id_base}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {**metadata, "chunk_index": c["chunk_index"],
                 "total_chunks": c["total_chunks"], "collection": collection}
                for c in chunks
            ]

            col.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )

            self.logger.info(f"Ingested {len(chunks)} chunks into '{collection}'")
            return TaskResult(
                success=True,
                data={
                    "doc_id": doc_id_base,
                    "chunks_ingested": len(chunks),
                    "collection": collection,
                    "title": metadata.get("title", ""),
                },
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e),
                              execution_time=asyncio.get_event_loop().time() - start)

    async def search(self, query: str, collection: str = "general",
                     top_k: int = 5, **kwargs) -> TaskResult:
        """
        Semantic search in a RAG collection.
        Returns top_k most relevant chunks with scores.
        """
        start = asyncio.get_event_loop().time()
        try:
            if not query or not query.strip():
                return TaskResult(success=False, error="Query cannot be empty")

            embedder = self._get_embedder()
            col = self._get_collection(collection)

            query_embedding = embedder.encode([query]).tolist()
            results = col.query(
                query_embeddings=query_embedding,
                n_results=min(top_k, col.count() or 1),
                include=["documents", "metadatas", "distances"]
            )

            hits = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    hits.append({
                        "text": doc,
                        "metadata": results["metadatas"][0][i],
                        "score": 1 - results["distances"][0][i],
                    })

            hits.sort(key=lambda x: x["score"], reverse=True)

            return TaskResult(
                success=True,
                data={"hits": hits, "count": len(hits), "collection": collection},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e),
                              execution_time=asyncio.get_event_loop().time() - start)

    async def forget(self, doc_id: str, collection: str = "general", **kwargs) -> TaskResult:
        """Remove all chunks of a document from a collection."""
        start = asyncio.get_event_loop().time()
        try:
            col = self._get_collection(collection)
            existing = col.get(where={"$contains": doc_id} if False else None)
            ids_to_delete = [
                id_ for id_ in (existing.get("ids") or [])
                if id_.startswith(doc_id)
            ]
            if ids_to_delete:
                col.delete(ids=ids_to_delete)
            return TaskResult(
                success=True,
                data={"deleted": len(ids_to_delete), "doc_id": doc_id},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def list_collections(self, **kwargs) -> TaskResult:
        """List all available RAG collections and their document counts."""
        start = asyncio.get_event_loop().time()
        try:
            client = self._get_client()
            collections = client.list_collections()
            result = []
            for col in collections:
                result.append({
                    "name": col.name,
                    "count": col.count(),
                })
            return TaskResult(
                success=True,
                data={"collections": result, "total": len(result)},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def ingest_room(self, room_name: str, content: str,
                          metadata: dict = None, **kwargs) -> TaskResult:
        """
        Ingest content from a Learning Room.
        Maps room names to dedicated collections.
        """
        room_collection_map = {
            "analista_esportivo": "rooms_esportes",
            "financeiro": "rooms_financeiro",
        }
        collection = room_collection_map.get(room_name, f"rooms_{room_name}")
        meta = metadata or {}
        meta.setdefault("source", f"room:{room_name}")
        meta.setdefault("topic", room_name)
        return await self.ingest(content, meta, collection=collection)

    async def search_room(self, room_name: str, query: str,
                          top_k: int = 5, **kwargs) -> TaskResult:
        """Search within a specific Learning Room collection."""
        room_collection_map = {
            "analista_esportivo": "rooms_esportes",
            "financeiro": "rooms_financeiro",
        }
        collection = room_collection_map.get(room_name, f"rooms_{room_name}")
        return await self.search(query, collection=collection, top_k=top_k)