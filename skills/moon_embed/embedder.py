"""
MoonEmbedder — wrapper around sentence-transformers.
Model: all-MiniLM-L6-v2 (384 dimensions, zero cost, local).
Consistent with MemoryAgent embedding model.
"""
import asyncio
import logging
from core.agent_base import TaskResult

logger = logging.getLogger(__name__)


class MoonEmbedder:
    """Generate embeddings using all-MiniLM-L6-v2 (same as MemoryAgent)."""

    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMENSIONS = 384

    def __init__(self):
        self._model = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.MODEL_NAME)
            self.logger.info(f"Model {self.MODEL_NAME} loaded ({self.DIMENSIONS}d)")
        return self._model

    async def embed_text(self, text: str, **kwargs) -> TaskResult:
        """Generate embedding vector for a single text."""
        start = asyncio.get_event_loop().time()
        try:
            if not text or not text.strip():
                return TaskResult(success=False, error="Text cannot be empty")
            model = self._get_model()
            vector = model.encode([text])[0].tolist()
            return TaskResult(
                success=True,
                data={"embedding": vector, "dimensions": len(vector), "text_length": len(text)},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def embed_batch(self, texts: list[str], **kwargs) -> TaskResult:
        """Generate embeddings for a batch of texts."""
        start = asyncio.get_event_loop().time()
        try:
            if not texts:
                return TaskResult(success=False, error="texts list cannot be empty")
            model = self._get_model()
            vectors = model.encode(texts).tolist()
            return TaskResult(
                success=True,
                data={"embeddings": vectors, "count": len(vectors),
                      "dimensions": self.DIMENSIONS},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    async def similarity(self, text_a: str, text_b: str, **kwargs) -> TaskResult:
        """Compute cosine similarity between two texts."""
        start = asyncio.get_event_loop().time()
        try:
            import numpy as np
            model = self._get_model()
            vecs = model.encode([text_a, text_b])
            cos_sim = float(np.dot(vecs[0], vecs[1]) /
                            (np.linalg.norm(vecs[0]) * np.linalg.norm(vecs[1])))
            return TaskResult(
                success=True,
                data={"similarity": cos_sim, "text_a_len": len(text_a),
                      "text_b_len": len(text_b)},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))