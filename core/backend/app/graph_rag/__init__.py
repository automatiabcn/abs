# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GraphRAG — entity/relation extraction + Neo4j↔Qdrant hybrid retrieval.

Phase 2 of the multi-tenant/GraphRAG roadmap. Layers a knowledge graph over
the existing RAG corpus: at (re)build time we extract entities + relations from
each chunk via the provider cascade and MERGE them into Neo4j (tenant-scoped,
Community-safe property isolation). At query time we do vector top-k in Qdrant,
expand 1-hop around the mentioned entities in Neo4j, then synthesize an answer
grounded in (chunks + subgraph) with chunk-level citations.
"""

from .extract import (
    ENTITY_TYPES,
    RELATION_TYPES,
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    entity_id,
    extract_graph,
)

__all__ = [
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "ExtractedEntity",
    "ExtractedRelation",
    "ExtractionResult",
    "entity_id",
    "extract_graph",
]
