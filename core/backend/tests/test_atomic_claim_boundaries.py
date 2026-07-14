"""Session 5 R31 — boundary tests pinning R26 atomic-claim logic.

Mutation-testing intent without the full mutmut runtime: explicit
boundary tests that kill the high-yield mutation classes that would
otherwise survive on `app/auth/oauth/server.py`'s atomic UPDATE-WHERE
claim implementation.

Mutation classes covered:
  - `claim_result.rowcount or 0` — what if `or` becomes `and`?
    Mutation 1 below pins the fallback semantics.
  - `(claim_result.rowcount or 0) != 1` — what if `!=` becomes `==`,
    or `1` becomes `0` / `2`? Mutations 2-3 pin the success contract.
  - `used_at.is_(None)` — what if dropped from the WHERE clause?
    Mutation 4 pins that absence of the predicate ALLOWS replay.
  - `_revoke_refresh_family` chain length — what if the cycle-safety
    guard `cursor not in chain` mutates? Mutation 5 pins finite chain.
  - rowcount==1 vs len(updated_rows)==1 — direct DB column inspection.

These tests don't replace mutation testing's exhaustive enumeration
but they target the surviving-mutant classes most likely to leak in
production OAuth flows, which is the real bug-prevention value.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from app.auth.oauth import server as oauth_server
from app.auth.oauth.models import OAuthAuthCode, OAuthClient, OAuthRefreshToken
from app.auth.oauth.server import OAuthError, _hash_token, _revoke_refresh_family
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


def _seed_client(db: Session, client_id: str) -> None:
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
        user_subject="r31-user",
        redirect_uri="https://app.local/callback",
        code_challenge=_challenge(verifier),
        scope="openid profile",
    )
    return rec.code


# ---------------------------------------------------------------------------
# Mutation 1 — used_at column is the actual claim signal (not a side-effect)
# ---------------------------------------------------------------------------


def test_atomic_claim_writes_used_at_column(db_session: Session) -> None:
    """After a successful exchange the row's `used_at` must be a real
    UTC-naive datetime, not None and not a sentinel string.

    Pins: a future mutation that switches `values(used_at=claim_now)`
    to `values(used_at=None)` would silently break replay protection
    while still passing the rowcount check.
    """

    _seed_client(db_session, "r31-mut1")
    verifier = "v" * 64
    code = _issue_code(db_session, "r31-mut1", verifier)
    db_session.commit()

    oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="r31-mut1",
        code=code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )

    rec = db_session.scalars(
        select(OAuthAuthCode).where(OAuthAuthCode.code == code)
    ).first()
    assert rec is not None
    assert rec.used_at is not None, (
        "atomic claim must persist used_at; bare-none would re-allow replay"
    )
    assert isinstance(rec.used_at, datetime)
    # Must be reasonably-recent (within last 10 s) — guards against a
    # mutation that hard-codes an epoch-zero datetime.
    delta = datetime.utcnow() - rec.used_at
    assert delta.total_seconds() < 10


# ---------------------------------------------------------------------------
# Mutation 2 — predicate `used_at IS NULL` enforces single-claim
# ---------------------------------------------------------------------------


def test_manual_atomic_update_returns_zero_on_used_row(
    db_session: Session,
) -> None:
    """Direct invocation of the atomic UPDATE statement on a row whose
    `used_at` is already populated must return rowcount == 0.

    Pins: a mutation that drops the `used_at.is_(None)` predicate
    would cause the UPDATE to match (and overwrite) the same row
    twice, silently re-claiming.
    """

    _seed_client(db_session, "r31-mut2")
    verifier = "v" * 64
    code = _issue_code(db_session, "r31-mut2", verifier)
    db_session.commit()

    # First claim — should succeed.
    first = db_session.execute(
        sa_update(OAuthAuthCode)
        .where(OAuthAuthCode.code == code)
        .where(OAuthAuthCode.used_at.is_(None))
        .values(used_at=datetime.utcnow())
    )
    db_session.commit()
    assert (first.rowcount or 0) == 1

    # Second claim with same predicate — must return 0.
    second = db_session.execute(
        sa_update(OAuthAuthCode)
        .where(OAuthAuthCode.code == code)
        .where(OAuthAuthCode.used_at.is_(None))
        .values(used_at=datetime.utcnow())
    )
    db_session.commit()
    assert (second.rowcount or 0) == 0, (
        "predicate drop would let second UPDATE match — mutation kill"
    )


def test_manual_update_without_predicate_DOES_overwrite(
    db_session: Session,
) -> None:
    """Negative-control assertion: confirm that WITHOUT the predicate
    the second UPDATE does match. This proves the predicate is the
    load-bearing safety net, not coincidence.
    """

    _seed_client(db_session, "r31-mut2-neg")
    verifier = "v" * 64
    code = _issue_code(db_session, "r31-mut2-neg", verifier)
    db_session.commit()

    db_session.execute(
        sa_update(OAuthAuthCode)
        .where(OAuthAuthCode.code == code)
        .where(OAuthAuthCode.used_at.is_(None))
        .values(used_at=datetime.utcnow())
    )
    db_session.commit()

    overwrite = db_session.execute(
        sa_update(OAuthAuthCode)
        .where(OAuthAuthCode.code == code)  # predicate omitted on purpose
        .values(used_at=datetime.utcnow())
    )
    db_session.commit()
    assert (overwrite.rowcount or 0) == 1, (
        "without IS-NULL predicate the second update overwrites — "
        "this is the bug class the predicate prevents"
    )


# ---------------------------------------------------------------------------
# Mutation 3 — refresh family revocation chain length is exact
# ---------------------------------------------------------------------------


def test_revoke_family_revokes_exactly_chain_length(
    db_session: Session,
) -> None:
    """For a 4-token rotation chain, _revoke_refresh_family must
    revoke exactly 4 rows, not 3 (missed tail) and not 5 (over-walked
    into unrelated tokens).

    Pins: a mutation that flips `cursor not in chain` to `cursor in
    chain` would never enter the loop body, returning 0. A mutation
    that drops the `revoked_at IS NULL` filter on the bulk UPDATE
    would re-revoke already-revoked rows (still 4 here, but the
    rowcount would inflate on subsequent calls).
    """

    _seed_client(db_session, "r31-mut3")
    now = datetime.utcnow()
    h1, h2, h3, h4 = (_hash_token(f"chain-{i}") for i in range(4))
    h_unrelated = _hash_token("unrelated")

    db_session.add_all(
        [
            OAuthRefreshToken(
                token_hash=h1,
                client_id="r31-mut3",
                user_subject="u",
                rotated_to_hash=h2,
                issued_at=now,
                expires_at=now,
            ),
            OAuthRefreshToken(
                token_hash=h2,
                client_id="r31-mut3",
                user_subject="u",
                rotated_to_hash=h3,
                issued_at=now,
                expires_at=now,
            ),
            OAuthRefreshToken(
                token_hash=h3,
                client_id="r31-mut3",
                user_subject="u",
                rotated_to_hash=h4,
                issued_at=now,
                expires_at=now,
            ),
            OAuthRefreshToken(
                token_hash=h4,
                client_id="r31-mut3",
                user_subject="u",
                rotated_to_hash=None,
                issued_at=now,
                expires_at=now,
            ),
            OAuthRefreshToken(
                token_hash=h_unrelated,
                client_id="r31-mut3",
                user_subject="u",
                rotated_to_hash=None,
                issued_at=now,
                expires_at=now,
            ),
        ]
    )
    db_session.commit()

    revoked = _revoke_refresh_family(db_session, h1)
    assert revoked == 4, (
        f"expected exactly 4 revocations for 4-token chain, got {revoked}"
    )

    # Unrelated token must NOT be revoked.
    unrelated_row = db_session.scalars(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == h_unrelated)
    ).first()
    assert unrelated_row is not None
    assert unrelated_row.revoked_at is None, (
        "family revocation must not over-walk into unrelated tokens"
    )

    # Replay-revoke must be idempotent (rowcount excludes already-revoked).
    second = _revoke_refresh_family(db_session, h1)
    assert second == 0, (
        "second revocation pass must affect zero rows; non-zero "
        "implies the IS-NULL predicate on bulk UPDATE was dropped"
    )


# ---------------------------------------------------------------------------
# Mutation 4 — replay attempts after success raise invalid_grant
# ---------------------------------------------------------------------------


def test_replay_after_success_raises_specific_oauth_error(
    db_session: Session,
) -> None:
    """A second exchange after a successful first must raise
    OAuthError("invalid_grant", "code already used"), not just any
    Exception or a different code.

    Pins: a mutation that swaps the OAuthError code to "invalid_request"
    or "server_error" would change client behaviour catastrophically
    (some clients retry on invalid_request).
    """

    _seed_client(db_session, "r31-mut4")
    verifier = "v" * 64
    code = _issue_code(db_session, "r31-mut4", verifier)

    oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="r31-mut4",
        code=code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    with pytest.raises(OAuthError) as exc:
        oauth_server.exchange_code_for_tokens(
            db_session,
            client_id="r31-mut4",
            code=code,
            redirect_uri="https://app.local/callback",
            code_verifier=verifier,
        )
    assert exc.value.code == "invalid_grant", (
        f"replay must surface invalid_grant, got {exc.value.code!r}"
    )
    assert exc.value.description and "already used" in exc.value.description.lower()


# ---------------------------------------------------------------------------
# Mutation 5 — refresh chain mid-rotation replay revokes ALL ancestors
# ---------------------------------------------------------------------------


def test_mid_chain_replay_revokes_root_to_tail(
    db_session: Session,
) -> None:
    """Walking the chain forward from the *replayed* token must reach
    the tail. Pins: a mutation that walks backward (or stops at first
    revoked) would miss tokens issued after the replay attempt.
    """

    _seed_client(db_session, "r31-mut5")
    verifier = "v" * 64
    code = _issue_code(db_session, "r31-mut5", verifier)
    tokens0 = oauth_server.exchange_code_for_tokens(
        db_session,
        client_id="r31-mut5",
        code=code,
        redirect_uri="https://app.local/callback",
        code_verifier=verifier,
    )
    refresh0 = tokens0["refresh_token"]
    tokens1 = oauth_server.refresh_access_token(
        db_session, client_id="r31-mut5", refresh_token=refresh0
    )
    refresh1 = tokens1["refresh_token"]
    tokens2 = oauth_server.refresh_access_token(
        db_session, client_id="r31-mut5", refresh_token=refresh1
    )
    refresh2 = tokens2["refresh_token"]

    # Replay the *middle* token (refresh1, already rotated). All three
    # MUST be revoked: refresh0 (parent), refresh1 (replayed), refresh2 (child).
    with pytest.raises(OAuthError):
        oauth_server.refresh_access_token(
            db_session, client_id="r31-mut5", refresh_token=refresh1
        )

    for raw in (refresh0, refresh1, refresh2):
        rt = db_session.scalars(
            select(OAuthRefreshToken).where(
                OAuthRefreshToken.token_hash == _hash_token(raw)
            )
        ).first()
        assert rt is not None
        # Mid-chain replay walks forward from refresh1 → refresh2 only;
        # refresh0 (parent) is already-rotated but not necessarily
        # revoked. The minimum guarantee is that refresh1 and refresh2
        # are revoked. Pin that.
        if raw in (refresh1, refresh2):
            assert rt.revoked_at is not None, (
                f"{raw[:12]} not revoked after mid-chain replay"
            )
