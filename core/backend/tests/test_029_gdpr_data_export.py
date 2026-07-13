"""029 Modul B — Data export build + endpoint tests."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.customer_audit.data_export import (
    create_export_job,
    decrypt_export,
    run_export_job,
)
from app.db.models import DataExportJob, License
from app.db.session import get_engine
from app.licensing import generate_license


def _make_license_row(jti: str, email: str = "alice@example.com") -> None:
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        if db.scalars(select(License).where(License.jti == jti)).first():
            return
        db.add(
            License(
                jti=jti,
                customer_email=email,
                tier="self-host",
                seat_count=1,
                issued_at=now,
                expires_at=now,
            )
        )
        db.commit()


def _issue_token_with_db_row(email: str = "alice@example.com"):
    import jwt as pyjwt

    token = generate_license("cust_e", valid_days=30)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    _make_license_row(jti, email)
    return token, jti, email


def test_build_zip_contains_all_files():
    token, jti, email = _issue_token_with_db_row()
    job = create_export_job(license_jti=jti, customer_email=email)
    result = run_export_job(job.job_id)
    assert result["ok"] is True

    with Session(get_engine()) as db:
        row = db.scalars(
            select(DataExportJob).where(DataExportJob.job_id == job.job_id)
        ).first()
        assert row is not None
        assert row.status == "done"
        path = row.output_path

    cipher = open(path, "rb").read()
    plaintext = decrypt_export(license_jti=jti, customer_email=email, ciphertext=cipher)

    with zipfile.ZipFile(io.BytesIO(plaintext)) as zf:
        names = set(zf.namelist())
    expected = {
        "README.txt",
        "license.json",
        "audit_log.jsonl",
        "webhook_events.jsonl",
        "email_queue.jsonl",
        "consents.jsonl",
        "connected_secrets.json",
    }
    assert expected.issubset(names)


def test_decrypt_with_wrong_email_fails():
    from cryptography.fernet import InvalidToken

    token, jti, email = _issue_token_with_db_row()
    job = create_export_job(license_jti=jti, customer_email=email)
    run_export_job(job.job_id)

    with Session(get_engine()) as db:
        row = db.scalars(
            select(DataExportJob).where(DataExportJob.job_id == job.job_id)
        ).first()
        path = row.output_path
    cipher = open(path, "rb").read()

    raised = False
    try:
        decrypt_export(
            license_jti=jti,
            customer_email="other@example.com",
            ciphertext=cipher,
        )
    except InvalidToken:
        raised = True
    assert raised is True


def test_data_export_endpoint_creates_job(client):
    token, _, _ = _issue_token_with_db_row()
    r = client.post(
        "/v1/me/data-export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["job_id"].startswith("dxj_")


def test_data_export_status_returns_download_url(client):
    token, _, _ = _issue_token_with_db_row()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/v1/me/data-export", headers=headers)
    job_id = r.json()["job_id"]
    r = client.get(f"/v1/me/data-export/{job_id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["download_url"].endswith("/download")
    assert body["size_bytes"] is not None and body["size_bytes"] > 0


def test_data_export_download_returns_bytes(client):
    token, jti, email = _issue_token_with_db_row()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/v1/me/data-export", headers=headers)
    job_id = r.json()["job_id"]
    r = client.get(
        f"/v1/me/data-export/{job_id}/download",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    plaintext = decrypt_export(
        license_jti=jti, customer_email=email, ciphertext=r.content
    )
    with zipfile.ZipFile(io.BytesIO(plaintext)) as zf:
        license_data = json.loads(zf.read("license.json"))
        assert license_data["jti"] == jti


def test_data_export_other_user_forbidden(client):
    """Owner-A creates an export, owner-B (different jti) cannot read it."""
    token_a, _, _ = _issue_token_with_db_row(email="a@example.com")
    r = client.post(
        "/v1/me/data-export", headers={"Authorization": f"Bearer {token_a}"}
    )
    job_id = r.json()["job_id"]

    token_b, _, _ = _issue_token_with_db_row(email="b@example.com")
    r = client.get(
        f"/v1/me/data-export/{job_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 403


def test_data_export_404_unknown_job(client):
    token, _, _ = _issue_token_with_db_row()
    r = client.get(
        "/v1/me/data-export/dxj_does_not_exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
