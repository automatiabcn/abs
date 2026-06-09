# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""CSV / JSON import adapter — the first REAL connector (Stage A).

No external auth: the tenant uploads a CSV/JSON of their companies/leads and
this imports them into the growth tables, so the data really flows into Lead
Intelligence / Context Graph / Dashboard. Flexible column mapping (TR + EN
header aliases). Dedup by company name (case-insensitive) within the tenant.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.connectors.adapters.base import ConnectorAdapter, CredentialField, SyncResult
from app.db.growth_models import Company, Contact, Lead
from app.db.session import get_engine

# header alias → canonical field
_ALIASES = {
    "company": "company", "firma": "company", "name": "company", "şirket": "company", "sirket": "company",
    "sector": "sector", "sektör": "sector", "sektor": "sector", "industry": "sector",
    "vkn": "vkn", "taxid": "vkn", "tax_id": "vkn",
    "domain": "domain", "website": "domain", "web": "domain",
    "contact": "contact_name", "contact_name": "contact_name", "yetkili": "contact_name", "kişi": "contact_name",
    "email": "contact_email", "contact_email": "contact_email", "eposta": "contact_email", "e-posta": "contact_email",
    "role": "contact_role", "contact_role": "contact_role", "rol": "contact_role", "title": "contact_role",
    "score": "score", "skor": "score",
    "intent": "intent", "niyet": "intent",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Safety bound on a single manual upload (the imported count is surfaced).
_MAX_ROWS = 5000


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _parse_rows(data: str, fmt: str) -> list[dict]:
    """Return a list of canonical-keyed dicts from CSV or JSON text."""
    fmt = (fmt or "").lower()
    raw: list[dict] = []
    text = (data or "").strip()
    if fmt == "json" or (not fmt and text[:1] in "[{"):
        parsed = json.loads(text)
        raw = parsed if isinstance(parsed, list) else parsed.get("rows", []) if isinstance(parsed, dict) else []
    else:
        reader = csv.DictReader(io.StringIO(text))
        raw = [dict(r) for r in reader]
    out: list[dict] = []
    for r in raw:
        canon: dict = {}
        for k, v in (r or {}).items():
            ck = _ALIASES.get(_norm(str(k)))
            if ck and v not in (None, ""):
                canon[ck] = str(v).strip()
        if canon.get("company"):
            out.append(canon)
        if len(out) >= _MAX_ROWS:           # bound a single upload
            break
    return out


def _to_score(v: str) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f > 1.0:           # percentage form (0..100) → 0..1
        f = f / 100.0
    return max(0.0, min(1.0, f))


def _intent(v: str, score: float) -> str:
    v = _norm(v)
    if v in ("high", "yüksek", "yuksek"):
        return "high"
    if v in ("medium", "orta"):
        return "medium"
    if v in ("watching", "izleniyor", "low", "düşük"):
        return "watching"
    return "high" if score >= 0.75 else "medium" if score >= 0.5 else "watching"


class CsvImportAdapter(ConnectorAdapter):
    connector_id = "csv_import"
    auth_kind = "file"
    credential_fields = [
        CredentialField(key="data", label="CSV / JSON içeriği", type="file"),
        CredentialField(key="format", label="Biçim (csv|json)", type="text", required=False),
    ]

    async def test_connection(self, creds: dict) -> tuple[bool, str]:
        try:
            rows = _parse_rows(creds.get("data", ""), creds.get("format", ""))
        except Exception as exc:  # malformed file
            return False, f"ayrıştırılamadı: {type(exc).__name__}: {str(exc)[:120]}"
        if not rows:
            return False, "geçerli satır yok (en az 'company/firma' sütunu gerekli)"
        return True, f"{len(rows)} satır geçerli"

    async def sync(self, tenant_slug: str, creds: dict) -> SyncResult:
        res = SyncResult()
        try:
            rows = _parse_rows(creds.get("data", ""), creds.get("format", ""))
        except Exception as exc:
            res.error = f"ayrıştırılamadı: {str(exc)[:160]}"
            return res
        with Session(get_engine()) as db:
            # Build the case-insensitive name→Company index ONCE (not per row) and
            # keep it current as we insert — dedup stays O(n) over the upload.
            by_name = {
                _norm(c.name): c
                for c in db.exec(select(Company).where(Company.tenant_slug == tenant_slug)).all()
            }
            for row in rows:
                cname = row["company"][:256]
                company = by_name.get(_norm(cname))
                if company is None:
                    company = Company(
                        tenant_slug=tenant_slug, name=cname,
                        sector=row.get("sector", "")[:96], vkn=row.get("vkn") or None,
                        domain=row.get("domain") or None, source="csv_import",
                    )
                    db.add(company)
                    db.commit()
                    db.refresh(company)
                    by_name[_norm(cname)] = company    # so later rows dedup too
                    res.companies += 1
                else:
                    if row.get("sector"):
                        company.sector = row["sector"][:96]
                    db.add(company)
                    db.commit()

                if row.get("contact_email"):
                    has = db.exec(
                        select(Contact).where(
                            Contact.tenant_slug == tenant_slug,
                            Contact.company_id == company.id,
                            Contact.email == row["contact_email"][:254],
                        )
                    ).first()
                    if not has:
                        db.add(Contact(
                            tenant_slug=tenant_slug, company_id=company.id,
                            name=row.get("contact_name", "")[:160] or row["contact_email"].split("@")[0],
                            email=row["contact_email"][:254], role=row.get("contact_role", "")[:96],
                        ))
                        res.contacts += 1

                # one lead per imported company (if none yet)
                lead = db.exec(
                    select(Lead).where(
                        Lead.tenant_slug == tenant_slug, Lead.company_id == company.id
                    )
                ).first()
                if not lead:
                    score = _to_score(row.get("score", ""))
                    db.add(Lead(
                        tenant_slug=tenant_slug, company_id=company.id, source="csv_import",
                        score=score, intent=_intent(row.get("intent", ""), score),
                        status="scored" if score else "new",
                    ))
                    res.leads += 1
            db.commit()
        return res
