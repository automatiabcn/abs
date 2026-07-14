"""Q12 L22 sweep 3 — OAuth 2.1 atomic single-use enforcement.

Two production-grade race vectors uncovered by Session 4 deep audit:

* **Q12-L22-005 (HIGH security)** — `exchange_code_for_tokens` performed a
  read-then-write on `OAuthAuthCode.used_at`. Two concurrent /oauth/token
  requests with the same authorization code could both pass the
  `used_at is None` guard and both mint access+refresh token pairs.
  OAuth 2.1 §4.1.3: authorization code MUST be single-use.

* **Q12-L22-006 (HIGH security)** — `refresh_access_token` performed the
  same read-then-write on `OAuthRefreshToken.rotated_to_hash`. Concurrent
  /oauth/token grant_type=refresh_token requests could both rotate the
  same parent refresh and mint independent token chains. OAuth 2.1 §6.1
  additionally requires that on detected refresh-replay the AS revoke
  the entire token family.

The fix introduces an atomic UPDATE-with-rowcount claim plus a
`_revoke_refresh_family` helper that walks the rotation chain forward
and bulk-revokes every hash in the lineage.
"""

from __future__ import annotations

import base64
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select

from app.auth.oauth import server as oauth_server
from app.auth.oauth.models import OAuthAuthCode, OAuthClient, OAuthRefreshToken
from app.auth.oauth.server import OAuthError
from app.db.session import get_engine


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


@pytest.fixture()
def db_session():
    with Session(get_engine()) as session:
        yield session


def _seed_client(db: Session, client_id: str = "race-client") -> None:
    db.add(
        OAuthClient(
            client_id=client_id,
            client_secret_hash=None,
            is_confidential=False,
            redirect_uris="https://app.local/callback",
            allowed_scopes="openid profile",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _issue_code(db: Session, client_id: str, verifier: str) -> str:
    rec = oauth_server.issue_authorization_code(
        db,
        client_id=client_id,
        user_subject="race-user",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
        scope="openid profile",
    )
    return rec.code


def _scalar_first(db: Session, stmt):
    return db.scalars(stmt).first()


# ---------------------------------------------------------------------------
# Q12-L22-005 — auth code atomic single-use
# ---------------------------------------------------------------------------


def test_two_session_replay_blocked(db_session: Session) -> None:
    """Two Session objects holding stale `used_at=None` ORM copies cannot
    both succeed: the atomic UPDATE-WHERE-used_at-IS-NULL fails on the
    loser, surfaced as invalid_grant.
    """

    _seed_client(db_session, client_id="race-005-a")
    verifier = "v" * 64
    code = _issue_code(db_session, "race-005-a", verifier)
    db_session.commit()

    sess_a = Session(get_engine())
    sess_b = Session(get_engine())
    try:
        rec_a = _scalar_first(
            sess_a, select(OAuthAuthCode).where(OAuthAuthCode.code == code)
        )
        rec_b = _scalar_first(
            sess_b, select(OAuthAuthCode).where(OAuthAuthCode.code == code)
        )
        assert rec_a is not None and rec_a.used_at is None
        assert rec_b is not None and rec_b.used_at is None

        tokens_a = oauth_server.exchange_code_for_tokens(
            sess_a,
            client_id="race-005-a",
            code=code,
            redirect_uri="https://app.local/callback",
            code_verifier=verifier,
        )
        assert tokens_a["access_token"]

        with pytest.raises(OAuthError) as exc:
            oauth_server.exchange_code_for_tokens(
                sess_b,
                client_id="race-005-a",
                code=code,
                redirect_uri="https://app.local/callback",
                code_verifier=verifier,
            )
        assert exc.value.code == "invalid_grant"
        assert "already used" in (exc.value.description or "").lower()
    finally:
        sess_a.close()
        sess_b.close()


def test_threaded_race_only_one_succeeds(db_session: Session) -> None:
    """Real-world threaded race: 2 concurrent exchanges with a
    barrier — exactly 1 success, 1 invalid_grant.
    """

    _seed_client(db_session, client_id="race-005-b")
    verifier = "v" * 64
    code = _issue_code(db_session, "race-005-b", verifier)
    db_session.commit()

    barrier = threading.Barrier(2)
    results: list[tuple[str, str]] = []
    lock = threading.Lock()

    def worker():
        try:
            with Session(get_engine()) as sess:
                barrier.wait(timeout=5.0)
                tokens = oauth_server.exchange_code_for_tokens(
                    sess,
                    client_id="race-005-b",
                    code=code,
                    redirect_uri="https://app.local/callback",
                    code_verifier=verifier,
                )
                with lock:
                    results.append(("ok", tokens["access_token"][:24]))
        except OAuthError as e:
            with lock:
                results.append(("err", e.code))
        except Exception as e:  # noqa: BLE001
            with lock:
                results.append(("exc", type(e).__name__))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for f in futures:
            f.result(timeout=10.0)

    successes = [r for r in results if r[0] == "ok"]
    errors = [r for r in results if r[0] == "err"]
    assert len(successes) == 1, f"expected 1 success, got {results}"
    assert len(errors) == 1, f"expected 1 invalid_grant, got {results}"
    assert errors[0][1] == "invalid_grant"


def test_post_use_replay_emits_warning(db_session: Session, caplog) -> None:
    """Sequential replay (post-commit) hits the fast-path guard and emits
    `oauth_code_replay_attempt` for ops visibility.
    """

    import logging

    _seed_client(db_session, client_id="race-005-c")
    verifier = "v" * 64
    code = _issue_code(db_session, "race-005-c", verifier)
    oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="race-005-c",
        code=code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    with caplog.at_level(logging.WARNING, logger="app.auth.oauth.server"):
        with pytest.raises(OAuthError) as exc:
            oauth_server.exchange_code_for_tokens(
                db_session,
                client_id="race-005-c",
                code=code,
                redirect_uri="https://app.local/callback",
                code_verifier=verifier,
            )
    assert exc.value.code == "invalid_grant"
    assert any("oauth_code_replay_attempt" in r.message for r in caplog.records), (
        "expected replay-attempt warning for ops audit"
    )


def test_normal_flow_still_works(db_session: Session) -> None:
    """Regression guard: single-shot exchange must mint token cleanly."""

    _seed_client(db_session, client_id="race-005-d")
    verifier = "v" * 64
    code = _issue_code(db_session, "race-005-d", verifier)
    tokens = oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="race-005-d",
        code=code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "Bearer"


# ---------------------------------------------------------------------------
# Q12-L22-006 — refresh rotation atomic + family revocation
# ---------------------------------------------------------------------------


def _bootstrap_refresh(db: Session, client_id: str) -> str:
    _seed_client(db, client_id=client_id)
    verifier = "v" * 64
    code = _issue_code(db, client_id, verifier)
    tokens = oauth_server.exchange_code_for_tokens(
        db,
        client_id=client_id,
        code=code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    db.commit()
    return tokens["refresh_token"]


def test_two_session_refresh_replay_blocked(db_session: Session) -> None:
    """Two stale ORM copies of the same refresh token: only one rotation
    survives; the loser is treated as replay → family revoked.
    """

    refresh = _bootstrap_refresh(db_session, "race-006-a")

    sess_a = Session(get_engine())
    sess_b = Session(get_engine())
    try:
        tokens_a = oauth_server.refresh_access_token(
            sess_a,
            client_id="race-006-a",
            refresh_token=refresh,
        )
        assert tokens_a["refresh_token"] != refresh

        with pytest.raises(OAuthError) as exc:
            oauth_server.refresh_access_token(
                sess_b,
                client_id="race-006-a",
                refresh_token=refresh,
            )
        assert exc.value.code == "invalid_grant"
    finally:
        sess_a.close()
        sess_b.close()


def test_threaded_refresh_race_only_one_succeeds(
    db_session: Session,
) -> None:
    """Concurrent refresh w/ same token → 1 success, 1 invalid_grant."""

    refresh = _bootstrap_refresh(db_session, "race-006-b")

    barrier = threading.Barrier(2)
    results: list[tuple[str, str]] = []
    lock = threading.Lock()

    def worker():
        try:
            with Session(get_engine()) as sess:
                barrier.wait(timeout=5.0)
                tokens = oauth_server.refresh_access_token(
                    sess,
                    client_id="race-006-b",
                    refresh_token=refresh,
                )
                with lock:
                    results.append(("ok", tokens["refresh_token"][:24]))
        except OAuthError as e:
            with lock:
                results.append(("err", e.code))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for f in futures:
            f.result(timeout=10.0)

    successes = [r for r in results if r[0] == "ok"]
    errors = [r for r in results if r[0] == "err"]
    assert len(successes) == 1, f"expected 1 success, got {results}"
    assert len(errors) == 1, f"expected 1 invalid_grant, got {results}"
    assert errors[0][1] == "invalid_grant"


def test_replay_revokes_family(db_session: Session) -> None:
    """OAuth 2.1 §6.1 — refresh-replay revokes the entire rotation chain
    so that a leaked-and-reused refresh cannot continue silently.
    """

    refresh_root = _bootstrap_refresh(db_session, "race-006-c")
    tokens_2 = oauth_server.refresh_access_token(
        db_session,
        client_id="race-006-c",
        refresh_token=refresh_root,
    )
    refresh_2 = tokens_2["refresh_token"]
    tokens_3 = oauth_server.refresh_access_token(
        db_session,
        client_id="race-006-c",
        refresh_token=refresh_2,
    )
    refresh_3 = tokens_3["refresh_token"]

    with pytest.raises(OAuthError) as exc:
        oauth_server.refresh_access_token(
            db_session,
            client_id="race-006-c",
            refresh_token=refresh_root,
        )
    assert exc.value.code == "invalid_grant"

    from app.auth.oauth.server import _hash_token

    for raw in (refresh_root, refresh_2, refresh_3):
        rt = _scalar_first(
            db_session,
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.token_hash == _hash_token(raw)
            ),
        )
        assert rt is not None
        assert rt.revoked_at is not None, (
            f"family member {raw[:16]} not revoked after replay"
        )

    with pytest.raises(OAuthError) as exc2:
        oauth_server.refresh_access_token(
            db_session,
            client_id="race-006-c",
            refresh_token=refresh_3,
        )
    assert exc2.value.code == "invalid_grant"


def test_replay_emits_warning(db_session: Session, caplog) -> None:
    """Replay attempts must emit `oauth_refresh_replay_blocked` for ops."""

    import logging

    refresh = _bootstrap_refresh(db_session, "race-006-d")
    oauth_server.refresh_access_token(
        db_session,
        client_id="race-006-d",
        refresh_token=refresh,
    )
    with caplog.at_level(logging.WARNING, logger="app.auth.oauth.server"):
        with pytest.raises(OAuthError):
            oauth_server.refresh_access_token(
                db_session,
                client_id="race-006-d",
                refresh_token=refresh,
            )
    assert any("oauth_refresh_replay_blocked" in r.message for r in caplog.records), (
        "expected replay-blocked warning for ops audit"
    )


def test_normal_rotation_unaffected(db_session: Session) -> None:
    """Regression guard: normal rotation chain keeps working."""

    refresh = _bootstrap_refresh(db_session, "race-006-e")
    for _ in range(3):
        tokens = oauth_server.refresh_access_token(
            db_session,
            client_id="race-006-e",
            refresh_token=refresh,
        )
        assert tokens["access_token"]
        assert tokens["refresh_token"] != refresh
        refresh = tokens["refresh_token"]


def test_revoke_family_cycle_safe(db_session: Session) -> None:
    """Defensive: family-walk handles a cyclical chain (corrupt data) by
    not looping forever.
    """

    from app.auth.oauth.server import _hash_token, _revoke_refresh_family

    _seed_client(db_session, client_id="race-006-f")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    h1 = _hash_token("aaaa")
    h2 = _hash_token("bbbb")
    db_session.add_all(
        [
            OAuthRefreshToken(
                token_hash=h1,
                client_id="race-006-f",
                user_subject="u",
                rotated_to_hash=h2,
                issued_at=now,
                expires_at=now,
            ),
            OAuthRefreshToken(
                token_hash=h2,
                client_id="race-006-f",
                user_subject="u",
                rotated_to_hash=h1,
                issued_at=now,
                expires_at=now,
            ),
        ]
    )
    db_session.commit()

    revoked = _revoke_refresh_family(db_session, h1)
    assert revoked == 2  # both, no infinite loop
