"""025 Modul B — Beta license generator script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine


def _load_script():
    repo = Path(__file__).resolve().parents[3]
    p = repo / "infra" / "scripts" / "generate_beta_license.py"
    spec = importlib.util.spec_from_file_location("generate_beta_license", p)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["generate_beta_license"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_generator_creates_jwt_and_db_row(capsys):
    mod = _load_script()
    rc = mod.main(
        [
            "--email",
            "beta-test1@x.co",
            "--tier",
            "self-host",
            "--duration-days",
            "60",
            "--no-email",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # JWT line
    assert "LICENSE=" in out
    # JSON output
    # Find the JSON part
    json_start = out.index("{")
    parsed = json.loads(out[json_start:])
    assert parsed["ok"] is True
    assert parsed["customer_email"] == "beta-test1@x.co"
    assert parsed["customer_id"].startswith("beta:")

    # DB row
    with Session(get_engine()) as s:
        row = s.scalars(
            select(License).where(License.jti == parsed["license_jti"])
        ).first()
        assert row is not None
        assert row.customer_email == "beta-test1@x.co"
        assert row.preferred_lang == "en"


def test_generator_team_tier_with_seat_count(capsys):
    mod = _load_script()
    rc = mod.main(
        [
            "--email",
            "beta-team@x.co",
            "--tier",
            "team",
            "--seat-count",
            "5",
            "--duration-days",
            "180",
            "--no-email",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out[out.index("{") :])
    assert parsed["tier"] == "team"
    assert parsed["seat_count"] == 5


def test_generator_lang_propagates_to_db(capsys):
    mod = _load_script()
    rc = mod.main(
        [
            "--email",
            "beta-tr@x.co",
            "--tier",
            "self-host",
            "--duration-days",
            "30",
            "--lang",
            "tr",
            "--no-email",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out[out.index("{") :])
    with Session(get_engine()) as s:
        row = s.scalars(
            select(License).where(License.jti == parsed["license_jti"])
        ).first()
        assert row.preferred_lang == "tr"


def test_beta_invitation_template_renders_all_3_langs():
    from app.email.sender import _render

    for lang in ("en", "tr", "es"):
        subject, html = _render(
            "beta_invitation.html",
            lang=lang,
            customer_email="user@x.co",
            license_key="eyJ.fake.token",
            expires_at="2026-10-25",
            duration_days=180,
        )
        assert "ABS" in subject
        assert "user@x.co" in html
        assert "eyJ.fake.token" in html
        assert "2026-10-25" in html
