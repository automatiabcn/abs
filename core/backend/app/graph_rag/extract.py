# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GraphRAG entity/relation extraction from chunk text via the LLM cascade.

Designed for EN + TR company documents (meeting transcripts, PDF/Word/Excel):
the entity taxonomy is business-oriented (Person/Organization/Project/…), not
academic. Output is normalized + deterministic so the same name resolves to the
same node across chunks/documents (idempotent MERGE downstream).

The LLM call is isolated in `_run_llm` so tests can monkeypatch it without
spinning up the provider stack.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Final

logger = logging.getLogger(__name__)

# Business-document entity taxonomy (EN + TR). The LLM is asked to use these
# canonical English type names; anything else is coerced to "Concept".
ENTITY_TYPES: Final[tuple[str, ...]] = (
    "Person",
    "Organization",
    "Project",
    "Concept",
    "Location",
    "Product",
    "Event",
    "Date",
)

# Allowed relationship types. Free-form predicates collapse to RELATED_TO so the
# graph stays queryable and the Neo4j label set bounded.
RELATION_TYPES: Final[tuple[str, ...]] = (
    "WORKS_AT",
    "PART_OF",
    "RELATED_TO",
    "INVOLVES",
    "LOCATED_IN",
    "RESPONSIBLE_FOR",
    "OWNS",
    "REPORTS_TO",
    "PRODUCES",
    "MENTIONS",
)

_ENTITY_TYPE_SET: Final[frozenset[str]] = frozenset(ENTITY_TYPES)
_RELATION_TYPE_SET: Final[frozenset[str]] = frozenset(RELATION_TYPES)

# Guardrails so a pathological chunk can't explode the graph or the prompt.
MAX_CHUNK_CHARS: Final[int] = 6000
MAX_ENTITIES_PER_CHUNK: Final[int] = 40
MAX_RELATIONS_PER_CHUNK: Final[int] = 60


@dataclass(slots=True, frozen=True)
class ExtractedEntity:
    id: str
    name: str
    type: str


@dataclass(slots=True, frozen=True)
class ExtractedRelation:
    source_id: str
    target_id: str
    type: str


@dataclass(slots=True)
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.entities and not self.relations


def _slug(name: str) -> str:
    """Accent-folded, lowercased, hyphenated slug.

    Turkish letters that NFKD does not decompose are folded explicitly, written
    as escapes to keep the source ASCII.
    """
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = folded.lower().replace("\u0131", "i").replace("\u015f", "s").replace("\u011f", "g")
    folded = folded.replace("\u00e7", "c").replace("\u00f6", "o").replace("\u00fc", "u")
    folded = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return folded


def entity_id(name: str, type_: str) -> str:
    """Deterministic, tenant-agnostic node id: `<type>:<slug(name)>`.

    Same name+type → same id across chunks and documents, so MERGE dedups.
    Tenant isolation is a node *property*, not part of the id (Community edition
    is single-DB; the same logical entity could appear in multiple tenants and
    each gets its own MERGE keyed on (id, tenant_id) downstream).
    """
    return f"{_norm_type(type_).lower()}:{_slug(name)}"


def _norm_type(raw: str | None) -> str:
    t = (raw or "").strip().title()
    # tolerate common synonyms the model emits
    synonyms = {
        "Org": "Organization",
        "Company": "Organization",
        "Firm": "Organization",
        "Place": "Location",
        "City": "Location",
        "Country": "Location",
        "People": "Person",
        "Human": "Person",
    }
    t = synonyms.get(t, t)
    return t if t in _ENTITY_TYPE_SET else "Concept"


def _norm_relation(raw: str | None) -> str:
    t = (raw or "").strip().upper().replace(" ", "_").replace("-", "_")
    return t if t in _RELATION_TYPE_SET else "RELATED_TO"


def _extract_json_obj(text: str) -> str:
    """Strip a ```json fence / surrounding prose down to the first balanced {…}."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    if s.startswith("{"):
        return s
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        return s[i : j + 1]
    return s


def build_extraction_prompt(text: str) -> str:
    types = ", ".join(ENTITY_TYPES)
    rels = ", ".join(RELATION_TYPES)
    return (
        "You are an information-extraction engine for business documents "
        "(English and Turkish: meeting transcripts, contracts, reports). "
        "Extract the named entities and the relationships between them from the "
        "passage below.\n\n"
        f"Entity `type` MUST be one of: {types}.\n"
        f"Relation `type` MUST be one of: {rels} (use RELATED_TO if unsure).\n"
        "Use the entity's exact surface name as it appears (do not translate). "
        "Only emit relations between entities you also list. Skip pronouns, "
        "filler, and generic words.\n\n"
        "Respond with the raw JSON object ONLY — no markdown fences, no prose — "
        "with this exact shape:\n"
        '{"entities": [{"name": "...", "type": "..."}], '
        '"relations": [{"source": "...", "target": "...", "type": "..."}]}\n'
        "where relation source/target are entity names from your entities list.\n\n"
        f"PASSAGE:\n{text[:MAX_CHUNK_CHARS]}"
    )


def _parse_extraction(raw_text: str) -> ExtractionResult | None:
    """Parse the LLM JSON into a normalized, de-duplicated ExtractionResult.

    Returns None when the payload is not parseable JSON with the expected shape
    (caller may retry with a stricter instruction).
    """
    try:
        obj = json.loads(_extract_json_obj(raw_text))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None

    by_id: dict[str, ExtractedEntity] = {}
    name_to_id: dict[str, str] = {}
    for item in (obj.get("entities") or [])[:MAX_ENTITIES_PER_CHUNK]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        etype = _norm_type(item.get("type"))
        eid = entity_id(name, etype)
        if eid not in by_id:
            by_id[eid] = ExtractedEntity(id=eid, name=name, type=etype)
        # map both the raw and lowercased name so relation lookup is forgiving
        name_to_id[name] = eid
        name_to_id[name.lower()] = eid

    rels: dict[tuple[str, str, str], ExtractedRelation] = {}
    for item in (obj.get("relations") or [])[:MAX_RELATIONS_PER_CHUNK]:
        if not isinstance(item, dict):
            continue
        src = str(item.get("source") or "").strip()
        dst = str(item.get("target") or "").strip()
        if not src or not dst:
            continue
        src_id = name_to_id.get(src) or name_to_id.get(src.lower())
        dst_id = name_to_id.get(dst) or name_to_id.get(dst.lower())
        if not src_id or not dst_id or src_id == dst_id:
            continue
        rtype = _norm_relation(item.get("type"))
        key = (src_id, dst_id, rtype)
        if key not in rels:
            rels[key] = ExtractedRelation(
                source_id=src_id, target_id=dst_id, type=rtype
            )

    return ExtractionResult(entities=list(by_id.values()), relations=list(rels.values()))


async def _run_llm(prompt: str, *, tenant_id: str, use_cache: bool = True) -> str:
    """Call the provider cascade and return the raw completion text.

    Isolated for testability + graceful degradation. Raises RuntimeError when no
    provider is configured so the caller can surface a 422/skip best-effort.
    """
    from app.cascade.orchestrator import call_with_cascade
    from app.providers.cascade import get_active_providers

    active = get_active_providers()
    if not active:
        raise RuntimeError("no_providers_configured")
    primary, *rest = active
    resp = await call_with_cascade(
        prompt,
        primary=primary,
        fallbacks=tuple(rest),
        tenant_id=tenant_id,
        use_cache=use_cache,
        max_tokens=1024,
        temperature=0.1,
    )
    return getattr(resp, "text", "") or ""


async def extract_graph(text: str, *, tenant_id: str = "_global") -> ExtractionResult:
    """Extract a normalized entity/relation graph from a chunk of text.

    Best-effort: returns an empty result for blank input. Retries once with a
    stricter JSON instruction if a free-tier model returns prose.
    """
    clean = (text or "").strip()
    if not clean:
        return ExtractionResult()
    prompt = build_extraction_prompt(clean)
    parsed = _parse_extraction(await _run_llm(prompt, tenant_id=tenant_id))
    if parsed is None:
        parsed = _parse_extraction(
            await _run_llm(
                prompt + "\n\nIMPORTANT: respond with the raw JSON object ONLY.",
                tenant_id=tenant_id,
                use_cache=False,
            )
        )
    if parsed is None:
        logger.info("graphrag extraction returned non-JSON; skipping chunk")
        return ExtractionResult()
    return parsed
