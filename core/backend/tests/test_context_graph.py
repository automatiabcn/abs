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
    a = leads.create_company(tenant_slug="tG", name="Demirel Yapı A.Ş.", vkn="1112223334")
    b = leads.create_company(tenant_slug="tG", name="Demirel Yapi", vkn="1112223334")
    # a lead hangs off the duplicate
    leads.create_lead(tenant_slug="tG", company_id=b, source="crm")

    report = resolve_companies(tenant_slug="tG")
    assert report["merged_count"] == 1
    assert report["merges"][0]["survivor_id"] == a   # oldest survives

    graph = context_graph_view(tenant_slug="tG")
    company_nodes = [n for n in graph["nodes"] if n["type"] == "company"]
    # only the canonical company remains in the graph
    assert any(n["id"] == f"company:{a}" for n in company_nodes)
    assert all(n["id"] != f"company:{b}" for n in company_nodes)
    # the duplicate's lead was reassigned to the survivor (edge present)
    assert any(e["source"] == f"company:{a}" and e["rel"] == "lead" for e in graph["edges"])


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
