"""Usage logger unit + integration tests."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1 import rag as rag_routes
from app.auth.oauth.models import OAuthClient
from app.config import settings
from app.db.session import get_engine
from app.main import app
from app.observability import usage_logger as ul


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "rag_usage.jsonl"
    monkeypatch.setattr(settings, "usage_log_path", str(target), raising=False)
    monkeypatch.setattr(settings, "usage_log_sample_rate", 1.0, raising=False)
    ul.close_usage_logger()
    yield
    ul.close_usage_logger()


def test_make_event_fills_defaults() -> None:
    e = ul.make_event(
        name="rag.query",
        request_type="query",
        status="ok",
        latency_ms=12.5,
    )
    assert e.name == "rag.query"
    assert len(e.trace_id) == 32
    assert e.timestamp.endswith("Z")
    assert e.metadata == {}


def test_record_appends_jsonl_line(tmp_path: Path) -> None:
    log = ul.UsageLogger(jsonl_path=tmp_path / "u.jsonl", sample_rate=1.0)
    e = ul.make_event(
        name="rag.ingest",
        tenant_id="t1",
        user_subject="alice",
        request_type="ingest",
        status="ok",
        latency_ms=42.0,
        input_tokens=100,
        output_tokens=5,
        model_version="bge-m3-mock",
    )
    assert log.record(e) is True
    log.close()
    payload = json.loads((tmp_path / "u.jsonl").read_text("utf-8").strip())
    assert payload["tenant_id"] == "t1"
    assert payload["latency_ms"] == 42.0
    assert payload["input_tokens"] == 100


def test_record_no_loss_for_ten_events(tmp_path: Path) -> None:
    log = ul.UsageLogger(jsonl_path=tmp_path / "u.jsonl", sample_rate=1.0)
    for i in range(10):
        log.record(
            ul.make_event(
                name="rag.query",
                request_type="query",
                status="ok",
                latency_ms=float(i),
                metadata={"i": i},
            )
        )
    log.close()
    lines = (tmp_path / "u.jsonl").read_text("utf-8").splitlines()
    assert len(lines) == 10
    parsed = [json.loads(line) for line in lines]
    assert [p["metadata"]["i"] for p in parsed] == list(range(10))


def test_sampling_zero_skips_all(tmp_path: Path) -> None:
    log = ul.UsageLogger(jsonl_path=tmp_path / "u.jsonl", sample_rate=0.0)
    sampled_in = 0
    for _ in range(20):
        if log.record(
            ul.make_event(
                name="rag.query",
                request_type="query",
                status="ok",
                latency_ms=1.0,
            )
        ):
            sampled_in += 1
    log.close()
    assert sampled_in == 0
    assert not (tmp_path / "u.jsonl").read_text("utf-8")


def test_sampling_one_keeps_all(tmp_path: Path) -> None:
    log = ul.UsageLogger(jsonl_path=tmp_path / "u.jsonl", sample_rate=1.0)
    for _ in range(5):
        assert log.record(
            ul.make_event(
                name="rag.query",
                request_type="query",
                status="ok",
                latency_ms=1.0,
            )
        )
    log.close()
    assert len((tmp_path / "u.jsonl").read_text("utf-8").splitlines()) == 5


def test_singleton_lazy_init_and_close(tmp_path: Path) -> None:
    a = ul.get_usage_logger()
    b = ul.get_usage_logger()
    assert a is b
    ul.close_usage_logger()
    c = ul.get_usage_logger()
    assert c is not a


def test_langfuse_names_are_canonical() -> None:
    assert ul.LANGFUSE_NAMES == {"rag.ingest", "rag.query", "rag.delete"}


def test_record_handles_write_error_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = ul.UsageLogger(jsonl_path=tmp_path / "u.jsonl", sample_rate=1.0)

    class _Boom:
        def write(self, _line):  # noqa: ANN001
            raise OSError("disk full")

    monkeypatch.setattr(log, "_file", _Boom())
    assert (
        log.record(
            ul.make_event(
                name="rag.query",
                request_type="query",
                status="ok",
                latency_ms=1.0,
            )
        )
        is False
    )


# ----- /v1/rag end-to-end logging --------------------------------------


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def _seed_client(client_id: str) -> None:
    with Session(get_engine()) as db:
        db.add(
            OAuthClient(
                client_id=client_id,
                redirect_uris="https://app.local/callback",
                allowed_scopes="openid profile",
                is_confidential=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()


def _issue(c, *, client_id, tenant_id, user_subject="alice"):
    verifier = "v" * 64
    auth = c.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "rag:query",
            "user_subject": user_subject,
            "tenant_id": tenant_id,
            "roles": "member",
        },
        follow_redirects=False,
    )
    code = auth.headers["location"].split("code=", 1)[1].split("&", 1)[0]
    tok = c.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": "https://app.local/callback",
            "code_verifier": verifier,
        },
    )
    return tok.json()["access_token"]


@pytest.fixture()
def cerbos_allow():
    class _AllowAll:
        def check_resources(self, *, principal, resources):  # noqa: ANN001
            entry = SimpleNamespace(is_allowed=lambda action: True)
            return SimpleNamespace(
                results=[entry], failed=lambda: False, status_code=200
            )

        def close(self) -> None:
            return None

    app.state.cerbos_client = _AllowAll()
    yield
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")


def test_rag_query_emits_usage_event(
    monkeypatch: pytest.MonkeyPatch, cerbos_allow
) -> None:
    cid = f"u16-{secrets.token_hex(3)}"
    _seed_client(cid)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(
        rag_routes.qc,
        "search",
        lambda *a, **k: [
            {
                "id": "d-0",
                "score": 0.5,
                "payload": {
                    "chunk_id": "d-0",
                    "doc_id": "d",
                    "seq": 0,
                    "text": "ok",
                    "tenant_id": "tenant-1",
                },
            }
        ],
    )

    with TestClient(app) as c:
        token = _issue(c, client_id=cid, tenant_id="tenant-1")
        r = c.post(
            "/v1/rag/query",
            json={"query": "hello world", "limit": 3},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 200, r.text

    log_path = Path(settings.usage_log_path)
    assert log_path.exists()
    lines = log_path.read_text("utf-8").splitlines()
    assert lines, "expected at least one usage log line"
    payload = json.loads(lines[-1])
    assert payload["name"] == "rag.query"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["request_type"] == "query"
    assert payload["status"] == "ok"
    assert payload["output_tokens"] == 1
    assert payload["metadata"]["hits"] == 1
