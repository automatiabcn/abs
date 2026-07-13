# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Entity Resolution + Growth Context Graph view."""

from __future__ import annotations

from app.graph_context import (
    context_graph_view,
    normalize_company_name,
    resolve_companies,
)
from app.leads import service as leads


def test_normalize_turkish_legal_suffix() -> None:
    a = normalize_company_name("Demirel Yapı A.Ş.")
    b = normalize_company_name("Demirel Yapi")
    assert a == b == "demirel yapi"
    assert normalize_company_name("Kaya İnşaat Ltd. Şti.") == "kaya insaat"


def test_entity_resolution_merges_by_vkn() -> None:
    a = leads.create_company(
        tenant_slug="tG", name="Demirel Yapı A.Ş.", vkn="1112223334"
    )
    b = leads.create_company(tenant_slug="tG", name="Demirel Yapi", vkn="1112223334")
    # a lead hangs off the duplicate
    leads.create_lead(tenant_slug="tG", company_id=b, source="crm")

    report = resolve_companies(tenant_slug="tG")
    assert report["merged_count"] == 1
    assert report["merges"][0]["survivor_id"] == a  # oldest survives

    graph = context_graph_view(tenant_slug="tG")
    company_nodes = [n for n in graph["nodes"] if n["type"] == "company"]
    # only the canonical company remains in the graph
    assert any(n["id"] == f"company:{a}" for n in company_nodes)
    assert all(n["id"] != f"company:{b}" for n in company_nodes)
    # the duplicate's lead was reassigned to the survivor (edge present)
    assert any(
        e["source"] == f"company:{a}" and e["rel"] == "lead" for e in graph["edges"]
    )


def test_entity_resolution_merges_three_dups_reassigns_all_children() -> None:
    """Multi-dup block: 3 companies share a VKN, each carries a lead. The
    survivor (oldest) must absorb ALL duplicates' children — guards the batched
    (.in_) reassignment so a duplicate's lead can't be left orphaned."""
    a = leads.create_company(tenant_slug="t3", name="Akın Yapı A.Ş.", vkn="9998887776")
    b = leads.create_company(tenant_slug="t3", name="Akin Yapi", vkn="9998887776")
    c = leads.create_company(tenant_slug="t3", name="AKIN YAPI LTD", vkn="9998887776")
    leads.create_lead(tenant_slug="t3", company_id=b, source="crm")
    leads.create_lead(tenant_slug="t3", company_id=c, source="web")

    report = resolve_companies(tenant_slug="t3")
    assert report["merged_count"] == 2  # b and c both folded into a
    assert all(m["survivor_id"] == a for m in report["merges"])

    graph = context_graph_view(tenant_slug="t3")
    company_nodes = [n for n in graph["nodes"] if n["type"] == "company"]
    assert [n["id"] for n in company_nodes] == [f"company:{a}"]  # only survivor
    # both reassigned leads now edge off the survivor
    lead_edges = [e for e in graph["edges"] if e["rel"] == "lead"]
    assert len(lead_edges) == 2
    assert all(e["source"] == f"company:{a}" for e in lead_edges)


def test_entity_resolution_merges_by_normalized_name() -> None:
    leads.create_company(tenant_slug="tN", name="Kaya İnşaat A.Ş.")
    leads.create_company(tenant_slug="tN", name="Kaya Insaat")
    report = resolve_companies(tenant_slug="tN")
    assert report["merged_count"] == 1


def test_graph_view_tenant_scoped() -> None:
    leads.create_company(tenant_slug="tGV", name="Solo A.Ş.")
    g = context_graph_view(tenant_slug="tGV")
    assert g["stats"]["companies"] >= 1
    assert context_graph_view(tenant_slug="tGV-empty")["stats"]["companies"] == 0
