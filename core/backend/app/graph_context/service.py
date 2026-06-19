# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Entity resolution + context-graph assembly. Tenant-scoped throughout."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlmodel import Session, select

from app.db.growth_models import Company, Contact, Lead, Opportunity
from app.db.session import get_engine

logger = logging.getLogger(__name__)

# Turkish legal-form suffixes stripped before name comparison (design doc §R1).
_SUFFIXES = [
    "anonim sirketi", "limited sirketi", "a.s.", "as", "ltd. sti.", "ltd sti",
    "ltd", "sti", "san. ve tic.", "san ve tic", "san. tic.", "sanayi", "ticaret",
    "a s", "ş", "şti", "a.ş.", "a.ş", "ltd.", "şti.",
]


# Map Turkish letters (both cases) to ASCII BEFORE casefold — `"İ".casefold()`
# yields "i"+U+0307 (combining dot), which a later `[^a-z0-9]` strip would turn
# into a space and split the word ("i nsaat"). Translating first avoids that.
_TR = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c",
})


def normalize_company_name(name: str) -> str:
    """Turkish-aware canonical key: ASCII-fold, lower, strip legal suffixes."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).translate(_TR).lower()
    # defensive: drop any remaining combining marks
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suf in sorted(_SUFFIXES, key=len, reverse=True):
        k = re.sub(r"[^a-z0-9 ]+", " ", suf.casefold())
        k = re.sub(r"\s+", " ", k).strip()
        if k and s.endswith(" " + k):
            s = s[: -len(k)].strip()
    return s


def _block_key(c: Company) -> str:
    """Deterministic blocking key: VKN > domain > normalized name."""
    if c.vkn and c.vkn.strip():
        return "vkn:" + c.vkn.strip()
    if c.domain and c.domain.strip():
        return "dom:" + c.domain.strip().lower()
    return "name:" + normalize_company_name(c.name)


def resolve_companies(*, tenant_slug: str) -> Dict[str, Any]:
    """Merge duplicate companies into one canonical row (within the tenant).

    Blocking by VKN / domain / normalized-name; the survivor is the oldest
    canonical row, its `merged_count` grows, and the duplicates' contacts /
    leads / opportunities are reassigned to it (history kept: dup → canonical
    False, not deleted)."""
    tenant_slug = (tenant_slug or "default").strip()
    merges: List[dict] = []
    with Session(get_engine()) as db:
        companies = list(
            db.exec(
                select(Company).where(
                    Company.tenant_slug == tenant_slug, Company.canonical == True  # noqa: E712
                )
            )
        )
        groups: Dict[str, List[Company]] = {}
        for c in companies:
            groups.setdefault(_block_key(c), []).append(c)

        for key, members in groups.items():
            if len(members) < 2:
                continue
            members.sort(key=lambda m: (m.created_at or datetime.now(timezone.utc)))
            survivor = members[0]
            dups = members[1:]
            dup_ids = [d.id for d in dups]
            # All dups in a block fold into the same survivor, so reassign their
            # children in one query per model (batched .in_) instead of one query
            # per (dup × model) — same result, no N+1 on the merge path.
            for model in (Contact, Lead, Opportunity):
                rows = list(
                    db.exec(select(model).where(
                        model.tenant_slug == tenant_slug,
                        model.company_id.in_(dup_ids),  # type: ignore[attr-defined]
                    ))
                )
                for r in rows:
                    r.company_id = survivor.id
                    db.add(r)
            for dup in dups:
                dup.canonical = False
                db.add(dup)
                survivor.merged_count += 1
                merges.append({"survivor_id": survivor.id, "merged_id": dup.id,
                               "block": key})
            survivor.match_confidence = min(1.0, 0.8 + 0.05 * survivor.merged_count)
            db.add(survivor)
        db.commit()
    return {"merges": merges, "merged_count": len(merges)}


def context_graph_view(*, tenant_slug: str, limit: int = 60) -> Dict[str, Any]:
    """Nodes (companies + contacts + leads + opportunities) + edges, for the
    Growth Context Graph screen. Tenant-scoped."""
    tenant_slug = (tenant_slug or "default").strip()
    nodes: List[dict] = []
    edges: List[dict] = []
    with Session(get_engine()) as db:
        companies = list(
            db.exec(
                select(Company).where(
                    Company.tenant_slug == tenant_slug, Company.canonical == True  # noqa: E712
                ).limit(limit)
            )
        )
        cids = [c.id for c in companies]
        for c in companies:
            nodes.append({"id": f"company:{c.id}", "type": "company", "label": c.name,
                          "lifecycle": c.lifecycle, "score": round(c.score, 2),
                          "merged_count": c.merged_count})
        if cids:
            for model, ntype, labeller in (
                (Contact, "contact", lambda r: r.name),
                (Lead, "lead", lambda r: f"lead#{r.id} ({r.intent})"),
                (Opportunity, "opportunity", lambda r: r.name),
            ):
                rows = list(
                    db.exec(select(model).where(
                        model.tenant_slug == tenant_slug,
                        model.company_id.in_(cids),  # type: ignore[attr-defined]
                    ).limit(limit * 3))
                )
                for r in rows:
                    nid = f"{ntype}:{r.id}"
                    nodes.append({"id": nid, "type": ntype, "label": labeller(r)})
                    edges.append({"source": f"company:{r.company_id}", "target": nid,
                                  "rel": ntype})
    # Match accuracy = mean canonical match_confidence; merges = source records
    # folded into canonicals (Σ merged_count − #canonicals).
    confs = [c.match_confidence for c in companies]
    merged = sum(max(0, c.merged_count - 1) for c in companies)
    stats = {
        "companies": len(companies),
        "nodes": len(nodes),
        "edges": len(edges),
        "match_accuracy": round(sum(confs) / len(confs), 3) if confs else 1.0,
        "merges": merged,
    }
    return {"nodes": nodes, "edges": edges, "stats": stats}
