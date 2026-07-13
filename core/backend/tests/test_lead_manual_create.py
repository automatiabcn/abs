# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Roadmap (e) — manual lead entry. POST /v1/leads accepts company-level detail
(sector/domain/location/size), not just a bare company name, so the operator can
actually add a lead from the panel form."""

from __future__ import annotations

import pytest

from sqlmodel import Session, select

from app.db.growth_models import Company
from app.db.session import get_engine


@pytest.fixture()
def admin_client(client):
    r = client.post(
        "/auth/login", json={"email": "admin@local", "password": "CHANGEME"}
    )
    assert r.status_code == 200, r.text
    return client


def test_create_lead_persists_company_detail(admin_client):
    r = admin_client.post(
        "/v1/leads",
        json={
            "company_name": "Acme Yapı A.Ş.",
            "sector": "İnşaat",
            "domain": "acme.example",
            "location": "İstanbul",
            "size": "11-50",
        },
    )
    assert r.status_code in (200, 201), r.text
    lead = r.json()
    assert lead["company_name"] == "Acme Yapı A.Ş."

    with Session(get_engine()) as db:
        co = db.exec(select(Company).where(Company.name == "Acme Yapı A.Ş.")).first()
    assert co is not None
    assert co.sector == "İnşaat"
    assert co.domain == "acme.example"
    assert co.location == "İstanbul"
    assert co.size == "11-50"
    assert co.source == "manual"


def test_create_lead_requires_company_name(admin_client):
    r = admin_client.post("/v1/leads", json={"sector": "X"})
    assert r.status_code == 422  # company_name is required
