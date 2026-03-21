"""
MoonChunker — contextual text chunking (Anthropic pattern).
Prepends document context to each chunk for improved RAG retrieval.
Reference: anthropics/claude-cookbooks/capabilities/contextual-embeddings
"""
from core.agent_base import TaskResult
import asyncio


class MoonChunker:
    """Split documents into contextual chunks for RAG ingestion."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    async def chunk(self, content: str, metadata: dict,
                    chunk_size: int = None, overlap: int = None,
                    **kwargs) -> TaskResult:
        """
        Split content into overlapping contextual chunks.
        Each chunk includes document context prefix (Anthropic pattern).
        """
        start = asyncio.get_event_loop().time()
        try:
            if not content or not content.strip():
                return TaskResult(success=False, error="Content cannot be empty")

            cs = chunk_size or self.chunk_size
            ov = overlap or self.overlap

            doc_context = self._build_context(metadata)
            words = content.split()
            chunks = []

            for i in range(0, len(words), cs - ov):
                chunk_words = words[i:i + cs]
                raw_text = " ".join(chunk_words)
                contextual_text = f"{doc_context}\n\n{raw_text}"
                chunks.append({
                    "index": len(chunks),
                    "raw_text": raw_text,
                    "contextual_text": contextual_text,
                    "word_count": len(chunk_words),
                    "metadata": {**metadata, "chunk_index": len(chunks)},
                })

            for chunk in chunks:
                chunk["total_chunks"] = len(chunks)
                chunk["metadata"]["total_chunks"] = len(chunks)

            return TaskResult(
                success=True,
                data={"chunks": chunks, "total": len(chunks),
                      "original_word_count": len(words)},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    def _build_context(self, metadata: dict) -> str:
        """Build document context prefix from metadata."""
        parts = []
        if metadata.get("title"):
            parts.append(f"Title: {metadata['title']}")
        if metadata.get("topic"):
            parts.append(f"Topic: {metadata['topic']}")
        if metadata.get("source"):
            parts.append(f"Source: {metadata['source']}")
        if metadata.get("date"):
            parts.append(f"Date: {metadata['date']}")
        return ". ".join(parts) + "." if parts else "Document."

    async def chunk_meeting_log(self, log_path: str,
                                room_name: str, **kwargs) -> TaskResult:
        """Special chunker for Learning Room meeting logs."""
        start = asyncio.get_event_loop().time()
        try:
            from pathlib import Path
            path = Path(log_path)
            if not path.exists():
                return TaskResult(success=False,
                                  error=f"Meeting log not found: {log_path}")
            content = path.read_text(encoding="utf-8")
            metadata = {
                "title": f"Meeting Log — {room_name}",
                "topic": room_name,
                "source": f"room:{room_name}",
                "log_path": str(path),
            }
            return await self.chunk(content, metadata)
        except Exception as e:
            return TaskResult(success=False, error=str(e))