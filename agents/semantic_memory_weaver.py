"""
agents/semantic_memory_weaver.py
Semantic Memory Weaver — Arquiteto de Conhecimento do Ecossistema The Moon.

Constrói e mantém um Grafo de Conhecimento (Knowledge Graph) local que:
  - Correlaciona domínios: apostas, pesquisa, commits, blog, sistema
  - Registra relações causais entre eventos e seus resultados
  - Permite buscas híbridas (semântica + travessia de grafo)
  - Consolida memórias antigas em insights de alto nível
  - Responde a perguntas complexas multi-domínio via LLM + grafo

ZERO CUSTO:
  - Embeddings: sentence-transformers (local) → sklearn TF-IDF → Jaccard (fallbacks)
  - LLM para tagging/síntese: Groq free tier (llama-3.1-8b-instant)
  - Persistência: JSON + numpy (local)

CHANGELOG (Moon Codex — Março 2026):
  - [ARCH] Agente criado: SemanticMemoryWeaver — Knowledge Graph local
  - [ARCH] EmbeddingEngine com 3 camadas de fallback (transformers/tfidf/jaccard)
  - [ARCH] KnowledgeGraph dirigido tipado com BFS causal chain
  - [ARCH] Persistência atômica: graph.json + embeddings.npz
  - [ARCH] Consolidação periódica de memórias antigas em SUMMARY nodes
  - [ARCH] 8 ações: remember, link, recall, why, timeline, query, stats, consolidate
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent_base import AgentBase, AgentPriority, TaskResult

logger = logging.getLogger("moon.agents.weaver")

# ─────────────────────────────────────────────────────────────
#  Storage paths
# ─────────────────────────────────────────────────────────────
WEAVER_DIR         = Path("learning/knowledge_graph")
GRAPH_FILE         = WEAVER_DIR / "graph.json"
EMBEDDINGS_FILE    = WEAVER_DIR / "embeddings.npz"
INSIGHTS_FILE      = WEAVER_DIR / "consolidated_insights.json"
CONSOLIDATION_INTERVAL = 3600   # seconds between auto-consolidation cycles
MAX_NODES_BEFORE_CONSOLIDATE = 200


# ─────────────────────────────────────────────────────────────
#  Schema
# ─────────────────────────────────────────────────────────────

class NodeType(str, Enum):
    EVENT    = "event"       # something that happened
    INSIGHT  = "insight"     # a learned lesson
    STRATEGY = "strategy"    # a plan or approach
    OUTCOME  = "outcome"     # result of an action (success/failure)
    COMMIT   = "commit"      # git commit / code change
    POST     = "post"        # blog post or content piece
    BET      = "bet"         # sports betting record
    RESEARCH = "research"    # research note or finding
    CONCEPT  = "concept"     # abstract idea / keyword cluster
    SUMMARY  = "summary"     # consolidated memory of a cluster


class Domain(str, Enum):
    BETTING  = "betting"
    BLOG     = "blog"
    CODE     = "code"
    RESEARCH = "research"
    SYSTEM   = "system"
    GENERAL  = "general"


class RelationType(str, Enum):
    CAUSED_BY    = "caused_by"    # A was caused by B
    LED_TO       = "led_to"       # A led to B
    SUPPORTS     = "supports"     # A provides evidence for B
    CONTRADICTS  = "contradicts"  # A contradicts B
    RELATED_TO   = "related_to"   # weak semantic link
    PART_OF      = "part_of"      # A is a component of B
    FOLLOWED_BY  = "followed_by"  # temporal sequence
    LEARNED_FROM = "learned_from" # A extracted insight from B
    SUMMARIZES   = "summarizes"   # A is a summary of B


@dataclass
class MemoryNode:
    id:         str
    type:       NodeType
    domain:     Domain
    content:    str                        # main text / description
    metadata:   Dict[str, Any]            # domain-specific payload
    tags:       List[str]
    timestamp:  float
    confidence: float = 1.0               # 0-1, used for edge weighting
    source:     str   = "manual"          # which agent/system created it
    embedding:  Optional[List[float]] = None  # stored separately in .npz

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["embedding"] = None  # never serialise embedding into JSON
        d["type"]   = self.type.value
        d["domain"] = self.domain.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryNode":
        d["type"]   = NodeType(d["type"])
        d["domain"] = Domain(d["domain"])
        d.setdefault("embedding", None)
        return cls(**d)


@dataclass
class MemoryEdge:
    source:   str
    target:   str
    relation: RelationType
    weight:   float = 1.0        # 0-1, semantic or causal strength
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["relation"] = self.relation.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryEdge":
        d["relation"] = RelationType(d["relation"])
        return cls(**d)


# ─────────────────────────────────────────────────────────────
#  Embedding Engine (zero-cost, layered fallback)
# ─────────────────────────────────────────────────────────────

class EmbeddingEngine:
    """
    Layered embedding strategy:
      1. sentence-transformers/all-MiniLM-L6-v2 (local, free, ~80MB)
      2. sklearn TF-IDF + SVD (pure Python, no GPU)
      3. Jaccard token overlap (ultra-fallback, no dependencies)
    """

    def __init__(self) -> None:
        self._model     = None
        self._tfidf     = None
        self._svd       = None
        self._corpus:   List[str] = []
        self._backend   = "none"
        self._dim       = 0

    def _try_load_transformers(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer
            self._model   = SentenceTransformer("all-MiniLM-L6-v2")
            self._backend = "sentence_transformers"
            self._dim     = 384
            logger.info("EmbeddingEngine: using sentence-transformers (all-MiniLM-L6-v2).")
            return True
        except Exception:
            return False

    def _try_load_tfidf(self) -> bool:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            self._tfidf   = TfidfVectorizer(max_features=5000, sublinear_tf=True)
            self._svd     = TruncatedSVD(n_components=128, random_state=42)
            self._backend = "tfidf_svd"
            self._dim     = 128
            logger.info("EmbeddingEngine: using TF-IDF + SVD fallback.")
            return True
        except Exception:
            return False

    def load(self) -> None:
        if not self._try_load_transformers():
            if not self._try_load_tfidf():
                self._backend = "jaccard"
                self._dim     = 0
                logger.warning("EmbeddingEngine: using Jaccard fallback (no ML libs).")

    def embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Returns list of float vectors, or None if backend is Jaccard."""
        if self._backend == "sentence_transformers":
            vecs = self._model.encode(texts, show_progress_bar=False)
            return vecs.tolist()

        if self._backend == "tfidf_svd":
            import numpy as np
            self._corpus.extend(texts)
            all_vecs = self._tfidf.fit_transform(self._corpus)
            all_vecs = self._svd.fit_transform(all_vecs)
            # Return only the last len(texts) rows
            result = all_vecs[-len(texts):]
            return result.tolist()

        return None  # Jaccard: no dense vectors

    def similarity(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity between two vectors."""
        import math
        dot   = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x ** 2 for x in a))
        mag_b = math.sqrt(sum(x ** 2 for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def jaccard_similarity(self, text_a: str, text_b: str) -> float:
        """Token-level Jaccard similarity (ultra-fallback)."""
        set_a = set(text_a.lower().split())
        set_b = set(text_b.lower().split())
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)


# ─────────────────────────────────────────────────────────────
#  Knowledge Graph (in-memory + JSON persistence)
# ─────────────────────────────────────────────────────────────

class KnowledgeGraph:
    """
    Directed, typed, weighted graph.
    Nodes: MemoryNode | Edges: MemoryEdge
    Persistence: GRAPH_FILE (JSON) + EMBEDDINGS_FILE (.npz)
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, MemoryNode] = {}
        self.edges: List[MemoryEdge]      = []
        # Adjacency index for fast traversal: node_id → [edge, ...]
        self._out: Dict[str, List[MemoryEdge]] = {}
        self._in:  Dict[str, List[MemoryEdge]] = {}

    # ── CRUD ────────────────────────────────────────────────

    def add_node(self, node: MemoryNode) -> None:
        self.nodes[node.id] = node
        self._out.setdefault(node.id, [])
        self._in.setdefault(node.id, [])

    def add_edge(self, edge: MemoryEdge) -> None:
        # Prevent duplicate edges (same source/target/relation)
        for existing in self._out.get(edge.source, []):
            if existing.target == edge.target and existing.relation == edge.relation:
                existing.weight = max(existing.weight, edge.weight)
                return
        self.edges.append(edge)
        self._out.setdefault(edge.source, []).append(edge)
        self._in.setdefault(edge.target, []).append(edge)

    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: str, direction: str = "out") -> List[MemoryNode]:
        """Returns connected nodes. direction: 'out', 'in', 'both'."""
        edges = []
        if direction in ("out", "both"):
            edges += self._out.get(node_id, [])
        if direction in ("in", "both"):
            edges += self._in.get(node_id, [])
        return [self.nodes[e.target if direction != "in" else e.source]
                for e in edges
                if (e.target if direction != "in" else e.source) in self.nodes]

    def get_edges_between(self, source: str, target: str) -> List[MemoryEdge]:
        return [e for e in self._out.get(source, []) if e.target == target]

    def find_path(self, start: str, end: str, max_depth: int = 5) -> Optional[List[str]]:
        """BFS shortest path between two nodes (returns list of node IDs)."""
        if start not in self.nodes or end not in self.nodes:
            return None
        queue = [(start, [start])]
        visited = {start}
        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            for edge in self._out.get(current, []):
                nxt = edge.target
                if nxt == end:
                    return path + [nxt]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
        return None

    def get_by_domain(self, domain: Domain) -> List[MemoryNode]:
        return [n for n in self.nodes.values() if n.domain == domain]

    def get_by_type(self, node_type: NodeType) -> List[MemoryNode]:
        return [n for n in self.nodes.values() if n.type == node_type]

    def get_recent(self, limit: int = 20) -> List[MemoryNode]:
        return sorted(self.nodes.values(), key=lambda n: n.timestamp, reverse=True)[:limit]

    # ── Persistence ─────────────────────────────────────────

    def save(self) -> None:
        WEAVER_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }
        tmp = GRAPH_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(GRAPH_FILE)  # atomic write

        # Save embeddings separately
        self._save_embeddings()
        logger.info(f"Graph saved: {len(self.nodes)} nodes, {len(self.edges)} edges.")

    def _save_embeddings(self) -> None:
        try:
            import numpy as np
            ids, vecs = [], []
            for nid, node in self.nodes.items():
                if node.embedding:
                    ids.append(nid)
                    vecs.append(node.embedding)
            if vecs:
                np.savez_compressed(
                    EMBEDDINGS_FILE,
                    ids=np.array(ids),
                    embeddings=np.array(vecs, dtype=np.float32),
                )
        except Exception as exc:
            logger.warning(f"Could not save embeddings: {exc}")

    def load(self) -> None:
        if not GRAPH_FILE.exists():
            logger.info("No existing graph found — starting fresh.")
            return
        try:
            data = json.loads(GRAPH_FILE.read_text())
            for nd in data.get("nodes", []):
                self.add_node(MemoryNode.from_dict(nd))
            for ed in data.get("edges", []):
                edge = MemoryEdge.from_dict(ed)
                self.edges.append(edge)
                self._out.setdefault(edge.source, []).append(edge)
                self._in.setdefault(edge.target, []).append(edge)
            self._load_embeddings()
            logger.info(f"Graph loaded: {len(self.nodes)} nodes, {len(self.edges)} edges.")
        except Exception as exc:
            logger.error(f"Failed to load graph: {exc}")

    def _load_embeddings(self) -> None:
        try:
            import numpy as np
            if not EMBEDDINGS_FILE.exists():
                return
            data = np.load(EMBEDDINGS_FILE, allow_pickle=False)
            for nid, vec in zip(data["ids"], data["embeddings"]):
                if nid in self.nodes:
                    self.nodes[nid].embedding = vec.tolist()
        except Exception as exc:
            logger.warning(f"Could not load embeddings: {exc}")


# ─────────────────────────────────────────────────────────────
#  Semantic Memory Weaver Agent
# ─────────────────────────────────────────────────────────────

class SemanticMemoryWeaver(AgentBase):
    """
    Semantic Memory Weaver — Knowledge Graph architect for The Moon ecosystem.

    Public actions (via execute):
      remember       → Add a memory node (auto-embeds + auto-tags via LLM)
      link           → Create an explicit edge between two nodes
      recall         → Hybrid semantic + graph search
      why            → Causal chain explanation ("why did X work?")
      timeline       → Temporal narrative for a domain or tag
      query          → Free-form NL query answered via graph + LLM synthesis
      stats          → Graph statistics
      consolidate    → Manually trigger memory consolidation
    """

    def __init__(self, groq_client=None) -> None:
        super().__init__()
        self.name        = "SemanticMemoryWeaver"
        self.description = (
            "Knowledge Graph architect: stores, correlates and reasons over "
            "cross-domain memories (bets, research, commits, blog, system)."
        )
        self.priority = AgentPriority.HIGH

        self.graph   = KnowledgeGraph()
        self.embedder = EmbeddingEngine()
        self._groq   = groq_client  # injected Groq async client

        self._consolidation_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        await super().initialize()
        loop = asyncio.get_event_loop()
        # Load graph and embeddings in thread pool (I/O bound)
        await loop.run_in_executor(None, self.graph.load)
        # Load embedding engine (may download model on first run)
        await loop.run_in_executor(None, self.embedder.load)

        self._stop_event.clear()
        self._consolidation_task = asyncio.create_task(
            self._consolidation_loop(), name="moon.weaver.consolidation"
        )
        logger.info(
            f"{self.name} initialized — "
            f"{len(self.graph.nodes)} nodes loaded, "
            f"embedding backend: {self.embedder._backend}."
        )

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._consolidation_task and not self._consolidation_task.done():
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                pass
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.graph.save)
        await super().shutdown()

    async def ping(self) -> bool:
        return not self._stop_event.is_set()

    # ═══════════════════════════════════════════════════════════
    #  Execute dispatch
    # ═══════════════════════════════════════════════════════════

    async def _execute(self, action: str, **kwargs: Any) -> TaskResult:
        match action:
            case "remember":
                return await self._action_remember(**kwargs)
            case "link":
                return await self._action_link(**kwargs)
            case "recall":
                return await self._action_recall(**kwargs)
            case "why":
                return await self._action_why(**kwargs)
            case "timeline":
                return await self._action_timeline(**kwargs)
            case "query":
                return await self._action_query(**kwargs)
            case "stats":
                return TaskResult(success=True, data=self._get_stats())
            case "consolidate":
                report = await self._consolidate_memories()
                return TaskResult(success=True, data={"report": report})
            case _:
                return TaskResult(success=False, error=f"Unknown action: '{action}'")

    # ═══════════════════════════════════════════════════════════
    #  Action: remember
    # ═══════════════════════════════════════════════════════════

    async def _action_remember(self, **kwargs: Any) -> TaskResult:
        """
        Stores a new memory in the graph.

        Required kwargs:
          content  (str)      — main text
          domain   (str)      — Domain enum value
          type     (str)      — NodeType enum value

        Optional kwargs:
          metadata (dict)     — domain-specific payload
          tags     (list)     — manual tags (auto-tags will be added)
          source   (str)      — originating agent
          confidence (float)
          outcome_of (str)    — node_id this is an outcome of (auto-creates causal edge)
          links_to   (list)   — list of {node_id, relation} dicts
        """
        content  = kwargs.get("content", "")
        if not content:
            return TaskResult(success=False, error="'content' is required.")

        try:
            domain  = Domain(kwargs.get("domain", "general"))
            ntype   = NodeType(kwargs.get("type", "event"))
        except ValueError as exc:
            return TaskResult(success=False, error=str(exc))

        # Auto-tag via LLM (non-blocking; fallback to empty)
        manual_tags = kwargs.get("tags", [])
        auto_tags   = await self._auto_tag(content, domain)
        all_tags    = list(set(manual_tags + auto_tags))

        node = MemoryNode(
            id         = str(uuid.uuid4()),
            type       = ntype,
            domain     = domain,
            content    = content,
            metadata   = kwargs.get("metadata", {}),
            tags       = all_tags,
            timestamp  = time.time(),
            confidence = float(kwargs.get("confidence", 1.0)),
            source     = kwargs.get("source", "manual"),
        )

        # Embed in thread pool
        node.embedding = await self._embed_texts([content])
        node.embedding = node.embedding[0] if node.embedding else None

        self.graph.add_node(node)

        # Auto-link: causal outcome edge
        outcome_of = kwargs.get("outcome_of")
        if outcome_of and outcome_of in self.graph.nodes:
            self.graph.add_edge(MemoryEdge(
                source   = outcome_of,
                target   = node.id,
                relation = RelationType.LED_TO,
                weight   = node.confidence,
            ))

        # Explicit links
        for link in kwargs.get("links_to", []):
            try:
                self.graph.add_edge(MemoryEdge(
                    source   = node.id,
                    target   = link["node_id"],
                    relation = RelationType(link.get("relation", "related_to")),
                    weight   = float(link.get("weight", 0.8)),
                ))
            except (KeyError, ValueError):
                pass

        # Auto-link to semantically similar existing nodes
        await self._auto_link_similar(node)

        # Persist asynchronously
        asyncio.ensure_future(
            asyncio.get_event_loop().run_in_executor(None, self.graph.save)
        )

        logger.info(f"Memory stored: [{ntype.value}/{domain.value}] {content[:60]}… (id={node.id[:8]})")
        return TaskResult(
            success=True,
            data={"node_id": node.id, "tags": all_tags, "type": ntype.value},
        )

    # ═══════════════════════════════════════════════════════════
    #  Action: link
    # ═══════════════════════════════════════════════════════════

    async def _action_link(self, **kwargs: Any) -> TaskResult:
        """Creates an explicit edge between two existing nodes."""
        source   = kwargs.get("source_id")
        target   = kwargs.get("target_id")
        relation = kwargs.get("relation", "related_to")

        if not source or not target:
            return TaskResult(success=False, error="'source_id' and 'target_id' are required.")
        if source not in self.graph.nodes:
            return TaskResult(success=False, error=f"Node '{source}' not found.")
        if target not in self.graph.nodes:
            return TaskResult(success=False, error=f"Node '{target}' not found.")

        try:
            rel = RelationType(relation)
        except ValueError:
            return TaskResult(success=False, error=f"Unknown relation: '{relation}'.")

        edge = MemoryEdge(
            source   = source,
            target   = target,
            relation = rel,
            weight   = float(kwargs.get("weight", 1.0)),
            metadata = kwargs.get("metadata", {}),
        )
        self.graph.add_edge(edge)
        asyncio.create_task(
            asyncio.get_event_loop().run_in_executor(None, self.graph.save)
        )
        return TaskResult(success=True, data={"linked": f"{source[:8]} → {target[:8]}", "relation": rel.value})

    # ═══════════════════════════════════════════════════════════
    #  Action: recall (hybrid search)
    # ═══════════════════════════════════════════════════════════

    async def _action_recall(self, **kwargs: Any) -> TaskResult:
        """
        Hybrid semantic + structural recall.
        kwargs:
          query   (str)  — free-text query
          domain  (str)  — optional domain filter
          type    (str)  — optional type filter
          limit   (int)  — max results (default 10)
          expand  (bool) — also return 1-hop neighbours (default False)
        """
        query  = kwargs.get("query", "")
        limit  = int(kwargs.get("limit", 10))
        expand = bool(kwargs.get("expand", False))

        if not query:
            recent = self.graph.get_recent(limit)
            return TaskResult(success=True, data={"nodes": [self._node_summary(n) for n in recent]})

        # Filter candidates
        candidates = list(self.graph.nodes.values())
        if kwargs.get("domain"):
            try:
                d = Domain(kwargs["domain"])
                candidates = [n for n in candidates if n.domain == d]
            except ValueError:
                pass
        if kwargs.get("type"):
            try:
                t = NodeType(kwargs["type"])
                candidates = [n for n in candidates if n.type == t]
            except ValueError:
                pass

        scored = await self._semantic_score(query, candidates)
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:limit]

        results = []
        seen = set()
        for node, score in top:
            if node.id in seen:
                continue
            seen.add(node.id)
            entry = self._node_summary(node)
            entry["relevance_score"] = round(score, 4)

            if expand:
                neighbours = self.graph.get_neighbors(node.id, direction="both")
                entry["neighbours"] = [self._node_summary(nb) for nb in neighbours[:5]]

            results.append(entry)

        return TaskResult(success=True, data={"nodes": results, "total": len(results)})

    # ═══════════════════════════════════════════════════════════
    #  Action: why (causal chain)
    # ═══════════════════════════════════════════════════════════

    async def _action_why(self, **kwargs: Any) -> TaskResult:
        """
        Explains why an outcome happened by tracing causal paths in the graph.
        kwargs:
          node_id  (str) — outcome node to explain
          depth    (int) — max causal chain depth (default 4)
        """
        node_id = kwargs.get("node_id")
        depth   = int(kwargs.get("depth", 4))

        if not node_id or node_id not in self.graph.nodes:
            return TaskResult(success=False, error=f"Node '{node_id}' not found.")

        target_node = self.graph.nodes[node_id]

        # Traverse incoming causal edges (BFS backwards)
        chain = self._trace_causal_chain(node_id, depth)
        chain_text = self._format_chain(chain, target_node)

        # Synthesise with LLM
        synthesis = await self._llm_synthesize(
            f"Dado o seguinte grafo de causalidade para o nó '{target_node.content[:100]}':\n"
            f"{chain_text}\n\n"
            f"Explique de forma clara e concisa por que esse resultado ocorreu e "
            f"quais foram os fatores determinantes.",
            max_tokens=500,
        )

        return TaskResult(
            success=True,
            data={
                "node":      self._node_summary(target_node),
                "chain":     chain,
                "chain_text": chain_text,
                "synthesis": synthesis,
            },
        )

    def _trace_causal_chain(self, node_id: str, max_depth: int) -> List[Dict]:
        """BFS backwards through causal edges (caused_by, led_to, learned_from)."""
        CAUSAL = {RelationType.CAUSED_BY, RelationType.LED_TO, RelationType.LEARNED_FROM}
        visited = set()
        chain   = []
        queue   = [(node_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            node = self.graph.nodes.get(current_id)
            if not node:
                continue

            in_edges = self.graph._in.get(current_id, [])
            for edge in in_edges:
                if edge.relation in CAUSAL and edge.source not in visited:
                    src_node = self.graph.nodes.get(edge.source)
                    if src_node:
                        chain.append({
                            "from":     self._node_summary(src_node),
                            "to":       self._node_summary(node),
                            "relation": edge.relation.value,
                            "weight":   edge.weight,
                            "depth":    depth,
                        })
                        queue.append((edge.source, depth + 1))

        return chain

    def _format_chain(self, chain: List[Dict], target: MemoryNode) -> str:
        if not chain:
            return f"Nenhuma cadeia causal encontrada para: {target.content[:80]}"
        lines = [f"Resultado: {target.content[:80]}"]
        for step in sorted(chain, key=lambda x: x["depth"]):
            arrow = "←" * (step["depth"] + 1)
            lines.append(
                f"  {arrow} [{step['relation']}] {step['from']['content'][:70]} "
                f"(força: {step['weight']:.2f})"
            )
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════
    #  Action: timeline
    # ═══════════════════════════════════════════════════════════

    async def _action_timeline(self, **kwargs: Any) -> TaskResult:
        """
        Temporal narrative for a domain or tag.
        kwargs:
          domain  (str) — optional domain filter
          tag     (str) — optional tag filter
          limit   (int) — default 20
        """
        domain_filter = kwargs.get("domain")
        tag_filter    = kwargs.get("tag")
        limit         = int(kwargs.get("limit", 20))

        nodes = list(self.graph.nodes.values())

        if domain_filter:
            try:
                d = Domain(domain_filter)
                nodes = [n for n in nodes if n.domain == d]
            except ValueError:
                pass

        if tag_filter:
            nodes = [n for n in nodes if tag_filter.lower() in [t.lower() for t in n.tags]]

        nodes.sort(key=lambda n: n.timestamp)
        nodes = nodes[:limit]

        timeline_entries = [
            {
                "timestamp":  time.strftime("%Y-%m-%d %H:%M", time.localtime(n.timestamp)),
                "node":       self._node_summary(n),
                "edges_out":  len(self.graph._out.get(n.id, [])),
                "edges_in":   len(self.graph._in.get(n.id, [])),
            }
            for n in nodes
        ]

        # Ask LLM for narrative
        if timeline_entries:
            narrative_input = "\n".join(
                f"[{e['timestamp']}] [{e['node']['type']}/{e['node']['domain']}] "
                f"{e['node']['content'][:80]}"
                for e in timeline_entries
            )
            narrative = await self._llm_synthesize(
                f"Com base nesta linha do tempo de eventos do sistema The Moon:\n{narrative_input}\n\n"
                f"Escreva uma narrativa cronológica coerente descrevendo a evolução, "
                f"padrões observados e insights principais.",
                max_tokens=600,
            )
        else:
            narrative = "Nenhum evento encontrado para os filtros aplicados."

        return TaskResult(
            success=True,
            data={
                "entries":   timeline_entries,
                "narrative": narrative,
                "count":     len(timeline_entries),
            },
        )

    # ═══════════════════════════════════════════════════════════
    #  Action: query (free-form NL over the graph)
    # ═══════════════════════════════════════════════════════════

    async def _action_query(self, **kwargs: Any) -> TaskResult:
        """
        Answers a free-form natural language question about the knowledge graph.
        kwargs:
          question (str) — the question
          depth    (int) — recall depth (default 15)
        """
        question = kwargs.get("question", "")
        depth    = int(kwargs.get("depth", 15))

        if not question:
            return TaskResult(success=False, error="'question' is required.")

        # Retrieve relevant context
        recall_result = await self._action_recall(query=question, limit=depth, expand=True)
        context_nodes = recall_result.data.get("nodes", [])

        if not context_nodes:
            return TaskResult(
                success=True,
                data={"answer": "Não encontrei memórias relevantes para responder a esta pergunta."},
            )

        # Build context string
        context_str = "\n---\n".join(
            f"[{n['type']}/{n['domain']}] {n['content']}"
            + (f"\nTags: {', '.join(n.get('tags', []))}" if n.get("tags") else "")
            + (f"\nNeighbours: " + "; ".join(nb["content"][:50] for nb in n.get("neighbours", []))
               if n.get("neighbours") else "")
            for n in context_nodes
        )

        answer = await self._llm_synthesize(
            f"Você é o Semantic Memory Weaver do ecossistema The Moon. "
            f"Com base nas memórias recuperadas do Knowledge Graph, responda:\n\n"
            f"PERGUNTA: {question}\n\n"
            f"CONTEXTO DO GRAFO:\n{context_str}\n\n"
            f"Responda com precisão, citando as fontes do grafo quando relevante.",
            max_tokens=700,
        )

        return TaskResult(
            success=True,
            data={
                "question":        question,
                "answer":          answer,
                "sources_used":    len(context_nodes),
                "source_node_ids": [n["id"] for n in context_nodes[:5]],
            },
        )

    # ═══════════════════════════════════════════════════════════
    #  Memory Consolidation
    # ═══════════════════════════════════════════════════════════

    async def _consolidation_loop(self) -> None:
        """Periodically consolidates dense clusters into summary nodes."""
        logger.info("Memory consolidation loop started.")
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=CONSOLIDATION_INTERVAL,
                )
                break
            except asyncio.TimeoutError:
                pass

            if len(self.graph.nodes) >= MAX_NODES_BEFORE_CONSOLIDATE:
                await self._consolidate_memories()

    async def _consolidate_memories(self) -> str:
        """
        Summarises clusters of old nodes into high-level SUMMARY nodes.
        Strategy: group nodes older than 7 days by domain, summarise with LLM,
        create a SUMMARY node, link all originals to it with SUMMARIZES edges.
        Returns a report string.
        """
        cutoff  = time.time() - 7 * 86400  # 7 days ago
        reports = []

        for domain in Domain:
            old_nodes = [
                n for n in self.graph.get_by_domain(domain)
                if n.timestamp < cutoff and n.type != NodeType.SUMMARY
            ]
            if len(old_nodes) < 5:
                continue

            # Sort by time, take up to 30 per batch
            old_nodes.sort(key=lambda n: n.timestamp)
            batch = old_nodes[:30]

            batch_text = "\n".join(
                f"[{time.strftime('%Y-%m-%d', time.localtime(n.timestamp))}] "
                f"[{n.type.value}] {n.content[:100]}"
                for n in batch
            )

            summary_text = await self._llm_synthesize(
                f"Consolide as seguintes memórias do domínio '{domain.value}' do sistema The Moon "
                f"em um resumo estratégico de alto nível (máx 300 palavras):\n\n{batch_text}",
                max_tokens=400,
            )

            if not summary_text:
                continue

            # Create summary node
            summary_node = MemoryNode(
                id        = str(uuid.uuid4()),
                type      = NodeType.SUMMARY,
                domain    = domain,
                content   = summary_text,
                metadata  = {
                    "consolidates": [n.id for n in batch],
                    "period_start": batch[0].timestamp,
                    "period_end":   batch[-1].timestamp,
                },
                tags      = [domain.value, "consolidated", "summary"],
                timestamp = time.time(),
                source    = self.name,
            )
            summary_node.embedding = await self._embed_texts([summary_text])
            summary_node.embedding = summary_node.embedding[0] if summary_node.embedding else None
            self.graph.add_node(summary_node)

            # Link all summarised nodes
            for node in batch:
                self.graph.add_edge(MemoryEdge(
                    source   = summary_node.id,
                    target   = node.id,
                    relation = RelationType.SUMMARIZES,
                    weight   = 0.9,
                ))

            reports.append(f"✅ {domain.value}: {len(batch)} nós consolidados em summary {summary_node.id[:8]}.")
            logger.info(f"Consolidated {len(batch)} nodes in domain {domain.value}.")

        if reports:
            asyncio.ensure_future(
                asyncio.get_event_loop().run_in_executor(None, self.graph.save)
            )

        return "\n".join(reports) if reports else "Nenhum cluster elegível para consolidação."

    # ═══════════════════════════════════════════════════════════
    #  Helpers — Embedding, Similarity, Auto-link
    # ═══════════════════════════════════════════════════════════

    async def _embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Runs embedding in a thread pool to avoid blocking the event loop."""
        if self.embedder._backend == "jaccard":
            return None
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self.embedder.embed, texts)
        except Exception as exc:
            logger.warning(f"Embedding failed: {exc}")
            return None

    async def _semantic_score(
        self, query: str, candidates: List[MemoryNode]
    ) -> List[Tuple[MemoryNode, float]]:
        """Returns (node, score) pairs using the best available similarity method."""
        if not candidates:
            return []

        # Dense vector similarity
        if self.embedder._backend != "jaccard":
            q_vecs = await self._embed_texts([query])
            if q_vecs:
                q_vec = q_vecs[0]
                scored = []
                for node in candidates:
                    if node.embedding:
                        score = self.embedder.similarity(q_vec, node.embedding)
                    else:
                        # Fallback to Jaccard for nodes without embeddings
                        score = self.embedder.jaccard_similarity(query, node.content)
                    scored.append((node, score))
                return scored

        # Jaccard fallback
        return [
            (node, self.embedder.jaccard_similarity(query, node.content))
            for node in candidates
        ]

    async def _auto_link_similar(self, new_node: MemoryNode, threshold: float = 0.75) -> None:
        """
        Automatically creates RELATED_TO edges to existing nodes
        with semantic similarity above threshold.
        """
        if not new_node.embedding:
            return

        candidates = [
            n for nid, n in self.graph.nodes.items()
            if nid != new_node.id and n.embedding and n.type != NodeType.SUMMARY
        ]

        for node in candidates:
            score = self.embedder.similarity(new_node.embedding, node.embedding)
            if score >= threshold:
                self.graph.add_edge(MemoryEdge(
                    source   = new_node.id,
                    target   = node.id,
                    relation = RelationType.RELATED_TO,
                    weight   = round(score, 4),
                    metadata = {"auto_linked": True},
                ))

    # ═══════════════════════════════════════════════════════════
    #  Helpers — LLM synthesis (Groq free tier)
    # ═══════════════════════════════════════════════════════════

    async def _auto_tag(self, content: str, domain: Domain) -> List[str]:
        """Uses Groq llama-3.1-8b-instant to extract 3-5 concise tags."""
        if not self._groq:
            return []
        prompt = (
            f"Extraia de 3 a 5 tags concisas (uma palavra cada) para classificar "
            f"este conteúdo do domínio '{domain.value}':\n\n{content[:500]}\n\n"
            f"Responda APENAS com as tags separadas por vírgula, sem explicação."
        )
        raw = await self._llm_call(prompt, max_tokens=60)
        if not raw:
            return []
        return [t.strip().lower() for t in raw.split(",") if t.strip()][:5]

    async def _llm_synthesize(self, prompt: str, max_tokens: int = 500) -> str:
        """Generic LLM synthesis via Groq. Returns empty string on failure."""
        if not self._groq:
            return "(LLM não disponível — síntese desabilitada)"
        return await self._llm_call(prompt, max_tokens=max_tokens) or ""

    async def _llm_call(self, prompt: str, max_tokens: int = 200) -> Optional[str]:
        """Low-level Groq call — uses llama-3.1-8b-instant for speed/cost."""
        try:
            response = await self._groq.chat.completions.create(
                model      = "llama-3.1-8b-instant",
                messages   = [{"role": "user", "content": prompt}],
                max_tokens = max_tokens,
                temperature= 0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning(f"LLM call failed: {exc}")
            return None

    # ═══════════════════════════════════════════════════════════
    #  Helpers — Formatting
    # ═══════════════════════════════════════════════════════════

    def _node_summary(self, node: MemoryNode) -> Dict[str, Any]:
        return {
            "id":        node.id,
            "type":      node.type.value,
            "domain":    node.domain.value,
            "content":   node.content[:120],
            "tags":      node.tags,
            "timestamp": time.strftime("%Y-%m-%d %H:%M", time.localtime(node.timestamp)),
            "source":    node.source,
            "confidence": node.confidence,
        }

    def _get_stats(self) -> Dict[str, Any]:
        nodes = self.graph.nodes
        by_type   = {}
        by_domain = {}
        for n in nodes.values():
            by_type[n.type.value]     = by_type.get(n.type.value, 0) + 1
            by_domain[n.domain.value] = by_domain.get(n.domain.value, 0) + 1

        embedded = sum(1 for n in nodes.values() if n.embedding)
        return {
            "total_nodes":     len(nodes),
            "total_edges":     len(self.graph.edges),
            "nodes_by_type":   by_type,
            "nodes_by_domain": by_domain,
            "embedded_nodes":  embedded,
            "embedding_backend": self.embedder._backend,
            "open_circuits":   [],  # compatibility with Orchestrator health report
        }
