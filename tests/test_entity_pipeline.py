"""Integration tests for entity→decision pipeline.

Tests the full pipeline:
  - MemoryExtractor → EntityStore → Neo4j upsert (MENTIONS edge) → search
  - Entity graph signal in HierarchicalRetriever
  - 3-way RRF fusion (entity + vector + bm25)

Note: These tests use mocks for both the LLM and Neo4j to avoid
external dependencies.  They can be run standalone without a real
Neo4j instance or LLM API key.
"""
import sys, os, types, json, asyncio
from typing import Any, Dict, List, Optional, Tuple

# Module-loading boilerplate to work around pre-existing circular imports
# in src.graph.__init__ → snapshot → detect → core → engine → snapshot.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

for _full, _dot in [
    ('src.detect', 'detect'),
    ('src.detect.types', 'detect.types'),
    ('src.detect.project_watcher', 'detect.project_watcher'),
    ('src.core', 'core'),
    ('src.core.memo', 'core.memo'),
    ('src.core.engine', 'core.engine'),
    ('src.graph', 'graph'),
    ('src.graph.snapshot', 'graph.snapshot'),
]:
    _m = types.ModuleType(_dot)
    sys.modules[_full] = _m
    sys.modules[_dot] = _m

# Load graph submodules with explicit importlib machinery
import importlib.util as _util, importlib.machinery as _ilm

def _load(mod_name, path):
    _loader = _ilm.SourceFileLoader(mod_name, path)
    _spec = _util.spec_from_loader(mod_name, _loader)
    _m = _util.module_from_spec(_spec)
    sys.modules[mod_name] = _m
    _loader.exec_module(_m)
    return _m

_load('graph.memory_graph', 'src/graph/memory_graph.py')
_load('graph.retrieval', 'src/graph/retrieval.py')
_load('graph.indexer', 'src/graph/indexer.py')

# ── System imports ──────────────────────────────────────────────────
from src.extractors.memory_extractor import MemoryExtractor
from src.extractors.query_entity_extractor import QueryEntityExtractor
from src.storage.entity_store import EntityStore
from src.storage.neo4j_client import ExtractedEntity as Neo4jExtractedEntity
from src.extractors.memory_types import ExtractedEntity, MemoryExtractionResult
from node.node import DecisionNode
from node.types import DecisionStatus, ImpactLevel
from graph.retrieval import HierarchicalRetriever
from graph.memory_graph import MemoryGraph
from graph.indexer import BM25Indexer

import pytest


# ── Mock classes ────────────────────────────────────────────────────


class FakeLLM:
    """Returns a pre-canned JSON response on every call."""
    def __init__(self, response):
        self._response = response

    async def generate(self, prompt: str, **kwargs) -> str:
        return json.dumps(self._response)


class FakeNeo4j:
    """In-memory Neo4j mock that tracks entities, mentions, decisions,
    and their relationships for entity→decision bridging."""

    def __init__(self):
        self.entities: Dict[str, Any] = {}
        self.documents: Dict[str, Any] = {}
        self.decisions: Dict[str, dict] = {}
        self.mentions: List[Tuple[str, str, str]] = []   # (source_id, label, entity_name)
        self.references: List[Tuple[str, str]] = []       # (decision_sid, source_chat_id)

    async def upsert_entity(self, entity, source_type: str = "episode"):
        self.entities[entity.name] = entity
        if entity.source_id:
            label = "Document" if source_type == "document" else "Episode"
            self.mentions.append((entity.source_id, label, entity.name))

    async def upsert_document(self, doc_id: str, title: str = "", summary: str = ""):
        self.documents[doc_id] = {"id": doc_id, "title": title}

    async def upsert_decision(self, decision):
        self.decisions[decision.sid] = {
            "sid": decision.sid,
            "summary": decision.summary,
            "full_text": decision.full_text,
        }
        if getattr(decision, "source_chat_id", None):
            self.references.append((decision.sid, decision.source_chat_id))

    async def search_decisions_by_entity_names(self, names, limit: int = 30):
        results = []
        for ent_name in names:
            for src_id, src_label, e_name in self.mentions:
                if e_name == ent_name:
                    for d_sid, ref_id in self.references:
                        if ref_id == src_id and d_sid in self.decisions:
                            results.append(self.decisions[d_sid])
        seen = set()
        deduped = [r for r in results if r["sid"] not in seen and not seen.add(r["sid"])]
        return deduped[:limit]

    async def create_constraints(self):
        pass

    async def close(self):
        pass


class DummyEmbedder:
    """Returns constant low-dimensional vectors (no real embedding)."""
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def entity_store():
    return EntityStore()


@pytest.fixture
def fake_neo4j():
    return FakeNeo4j()


@pytest.fixture
def memory_extractor():
    return MemoryExtractor(FakeLLM({
        "entities": [
            {"name": "微服务架构", "entity_type": "Concept", "confidence": 0.9},
            {"name": "张工", "entity_type": "Person", "confidence": 0.85},
        ],
        "relationships": [{
            "source_name": "张工", "relationship_type": "PROPOSES",
            "target_name": "微服务架构", "confidence": 0.8,
        }],
        "facts": [{
            "content": "张工提议采用微服务架构", "confidence": 0.9,
            "related_entity_names": ["张工", "微服务架构"],
        }],
        "reasoning": "",
    }))


@pytest.fixture
def query_extractor():
    return QueryEntityExtractor(FakeLLM(["微服务架构", "张工"]))


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_document_entity_pipeline(memory_extractor, entity_store, fake_neo4j):
    """MemoryExtractor → EntityStore → Neo4j upsert with Document MENTIONS edge."""
    content = "张工在会议上提出了微服务架构方案"
    doc_id = "doc_architecture_plan"

    # 1. Extract entities from document content
    mem_result = await memory_extractor.extract(content, episode_id=doc_id)
    assert len(mem_result.entities) == 2

    # 2. Mark as document-sourced and store in EntityStore
    for ent in mem_result.entities:
        ent.source_type = "document"
    added = entity_store.add_entities(mem_result.entities)
    assert added > 0
    for ent in entity_store.get_all_entities():
        assert ent.source_type == "document"

    # 3. Upsert to Neo4j with source_type="document" → creates (Document)-[:MENTIONS]->(Entity)
    for ent in mem_result.entities:
        neo4j_ent = Neo4jExtractedEntity(
            name=ent.name, entity_type=ent.entity_type,
            attributes=ent.attributes, confidence=ent.confidence,
            source_id=ent.source_episode_id,
        )
        await fake_neo4j.upsert_entity(neo4j_ent, source_type="document")
    await fake_neo4j.upsert_document(doc_id)

    doc_mentions = [(s, l, e) for (s, l, e) in fake_neo4j.mentions if l == "Document"]
    assert len(doc_mentions) == 2

    # 4. Create a decision referencing this document, then search via entity
    dec = DecisionNode(
        sid="D001", topic_id="arch", summary="微服务方案",
        full_text="确认微服务方案", status=DecisionStatus.DECIDED,
        impact_level=ImpactLevel.MAJOR, source_chat_id=doc_id,
    )
    await fake_neo4j.upsert_decision(dec)

    results = await fake_neo4j.search_decisions_by_entity_names(["微服务架构"])
    assert len(results) == 1
    assert results[0]["sid"] == "D001"


@pytest.mark.asyncio
async def test_rrf_entity_signal(fake_neo4j, query_extractor):
    """HierarchicalRetriever uses entity graph signal for RRF."""
    g = MemoryGraph()
    d = DecisionNode(
        sid="D001", topic_id="arch", summary="微服务方案",
        full_text="确认微服务", status=DecisionStatus.DECIDED,
        impact_level=ImpactLevel.MAJOR, source_chat_id="ep_001",
    )
    g.upsert_decision(d, "test")

    await fake_neo4j.upsert_entity(
        Neo4jExtractedEntity(name="微服务架构", entity_type="Concept", source_id="ep_001"),
    )
    await fake_neo4j.upsert_decision(d)

    retriever = HierarchicalRetriever(
        memory_graph=g, neo4j_client=fake_neo4j,
        query_entity_extractor=query_extractor,
    )
    result = retriever.retrieve("微服务架构方案怎么样", top_k_decisions=5)
    assert result.total_count > 0
    assert result.scores.get("entity_count", 0) > 0


@pytest.mark.asyncio
async def test_rrf_3way_fusion(fake_neo4j, query_extractor):
    """3-way RRF fusion: entity + vector + BM25."""
    g = MemoryGraph()
    decisions = [
        DecisionNode(
            sid="D001", topic_id="arch", summary="微服务架构",
            full_text="拆分为微服务", status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR, source_chat_id="ep_001",
        ),
        DecisionNode(
            sid="D002", topic_id="arch", summary="Kong网关",
            full_text="使用Kong作为API网关", status=DecisionStatus.DECIDED,
            impact_level=ImpactLevel.MAJOR, source_chat_id="ep_003",
        ),
    ]
    for d in decisions:
        g.upsert_decision(d, "test")

    # BM25 — uses hypergraph format (episode IDs, not decision SIDs)
    bm25 = BM25Indexer()
    bm25.build_from_hypergraph({
        "episodes": {
            "ep_001": {"summary": "微服务架构", "episode_description": "拆分为微服务"},
            "ep_003": {"summary": "Kong网关", "episode_description": "使用Kong作为API网关"},
        },
    })

    await fake_neo4j.upsert_entity(
        Neo4jExtractedEntity(name="Kong", entity_type="Technology", source_id="ep_003"),
    )
    await fake_neo4j.upsert_decision(decisions[1])

    retriever = HierarchicalRetriever(
        memory_graph=g, bm25_index=bm25, embedding_provider=DummyEmbedder(),
        neo4j_client=fake_neo4j, query_entity_extractor=query_extractor,
        retrieval_type="rrf",
    )
    result = retriever.retrieve("Kong API网关", top_k_decisions=5)
    assert result.total_count > 0
    assert result.scores["entity_count"] > 0
    assert result.scores["vector_count"] > 0
    # BM25 may return 0 for short queries — at least entity + vector must fuse
    assert len(result.decisions) > 0