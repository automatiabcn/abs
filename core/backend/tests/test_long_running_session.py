"""long-running session JWT lifecycle.

The original L26 brief asked for a 24h-idle browser-tab Playwright
test with token refresh + memory-leak heap snapshots. Frontend dev
server is not running in this CI env, so the browser-level surface
is deferred. The backend invariants that underpin the L26 promise
ARE testable here:

  1. A cookie whose JWT exp is in the past (1s ago, 1h ago, 24h
     ago, 7d ago) gets a clean 401 — never a 500 / stack trace /
     missing audit event.
  2. The audit event reason discriminates `expired` vs `invalid`
     without relying on the (i18n-mutable) `detail` string. The
     refactor introduces typed `_SessionExpired` / `_SessionInvalid`
     exceptions so emit_event reads the *exception class*, not a
     string match. The earlier code used `"expiry" in detail` — locale
     drift would silently misroute every expired-session audit.
  3. A tampered JWT (mutated payload, valid base64) gets the
     `invalid` audit reason, NOT `expired`.
  4. OAuth refresh-token rotation is single-use *and* the second
     attempt produces a deterministic invalid_grant (existing
     contract — pin to L26 to guard against regression).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
import jwt as session_jwt

from app.observability.audit import LOGGER_NAME


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _make_cookie(seconds_ago: int) -> str:
    """Mint a JWT with iat/exp in the past (so it's already expired)."""
    from app.config import settings

    now = datetime.now(tz=timezone.utc)
    iat = now - timedelta(seconds=seconds_ago + 60)
    exp = now - timedelta(seconds=seconds_ago)
    payload = {
        "sub": "longsession@l26.test",
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return session_jwt.encode(payload, settings.session_secret, algorithm="HS256")


# ----------------------------------------------------------------------
# 1) Expired-cookie clean 401 + correct audit reason
# ----------------------------------------------------------------------


class TestExpiredSessionAuditReason:
    @pytest.mark.parametrize(
        "expired_seconds_ago",
        [1, 3600, 86400, 7 * 86400, 30 * 86400],
        ids=["1s", "1h", "24h", "7d", "30d"],
    )
    def test_expired_cookie_returns_401_with_expired_reason(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        expired_seconds_ago: int,
    ) -> None:
        cookie = _make_cookie(seconds_ago=expired_seconds_ago)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/auth/me", cookies={"abs_session": cookie})
        assert r.status_code == 401, (
            f"expired cookie ({expired_seconds_ago}s ago) "
            f"must return 401 cleanly, got {r.status_code}"
        )
        decoded_audits = [
            getattr(rec, "audit", {})
            for rec in caplog.records
            if rec.name == LOGGER_NAME
            and getattr(rec, "audit", {}).get("action") == "auth.session.decode"
        ]
        assert decoded_audits, "expired cookie must emit auth.session.decode audit"
        last = decoded_audits[-1]
        assert last["reason"] == "expired", (
            f"REGRESSION: expired cookie audit reason should be "
            f"'expired', got {last['reason']!r}. Locale-string drift "
            "would silently misroute the reason — fixed via typed "
            "_SessionExpired exception."
        )
        assert last["outcome"] == "denied"
        assert "request_id" in last  # the established contract


# ----------------------------------------------------------------------
# 2) Tampered JWT → invalid (NOT expired)
# ----------------------------------------------------------------------


class TestTamperedSessionAuditReason:
    def test_tampered_cookie_returns_401_with_invalid_reason(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Mint a valid current-time cookie then flip a payload byte.
        from app.config import settings

        now = datetime.now(tz=timezone.utc)
        valid = session_jwt.encode(
            {
                "sub": "x@l26.test",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(seconds=3600)).timestamp()),
            },
            settings.session_secret,
            algorithm="HS256",
        )
        # Flip a char in the signature segment — keeps base64 valid
        # but breaks signature verification.
        head, mid, sig = valid.split(".")
        flipped_sig = ("a" if sig[0] != "a" else "b") + sig[1:]
        tampered = f"{head}.{mid}.{flipped_sig}"

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/auth/me", cookies={"abs_session": tampered})

        assert r.status_code == 401
        last = [
            getattr(rec, "audit", {})
            for rec in caplog.records
            if rec.name == LOGGER_NAME
            and getattr(rec, "audit", {}).get("action") == "auth.session.decode"
        ][-1]
        assert last["reason"] == "invalid", (
            f"tampered JWT must surface as reason='invalid' "
            f"(distinct from 'expired'), got {last['reason']!r}"
        )

    def test_garbled_cookie_returns_401_with_invalid_reason(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/auth/me", cookies={"abs_session": "definitely.not.a.jwt"})
        assert r.status_code == 401
        decoded = [
            getattr(rec, "audit", {})
            for rec in caplog.records
            if rec.name == LOGGER_NAME
            and getattr(rec, "audit", {}).get("action") == "auth.session.decode"
        ]
        assert decoded and decoded[-1]["reason"] == "invalid"


# ----------------------------------------------------------------------
# 3) No double-emission on the missing-cookie path (audit hygiene)
# ----------------------------------------------------------------------


class TestAuditEmissionHygiene:
    def test_missing_cookie_emits_check_not_decode(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing cookie must hit `auth.me.check` (or session.check
        for protected routes) — NOT `auth.session.decode` (which is
        decode-failure specific). Pin to prevent reason-routing
        regressions when the audit pipeline is refactored.
        """
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/auth/me")
        assert r.status_code == 401

        decode_events = [
            rec
            for rec in caplog.records
            if rec.name == LOGGER_NAME
            and getattr(rec, "audit", {}).get("action") == "auth.session.decode"
        ]
        check_events = [
            rec
            for rec in caplog.records
            if rec.name == LOGGER_NAME
            and getattr(rec, "audit", {}).get("action")
            in ("auth.me.check", "auth.session.check")
        ]
        assert not decode_events, "missing cookie must NOT trigger auth.session.decode"
        assert check_events, "missing cookie should emit auth.me.check"


# ----------------------------------------------------------------------
# 4) OAuth refresh token single-use rotation (HTTP layer pin)
# ----------------------------------------------------------------------


class TestOAuthRefreshSingleUse:
    """Function-level rotation has a test (test_oauth_server.py).
    L26 pins the contract at the *function* layer too — the long-
    running session brief specifies this invariant must hold across
    the lifetime of a refresh chain so a stolen token can't be
    replayed indefinitely.
    """

    def test_refresh_token_second_use_rejected(self) -> None:
        import base64
        import hashlib
        from datetime import datetime, timezone

        from sqlmodel import Session

        from app.auth.oauth import server as oauth_server
        from app.auth.oauth.models import OAuthClient
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            client_id = "l26-refresh"
            db.add(
                OAuthClient(
                    client_id=client_id,
                    client_secret_hash=None,
                    is_confidential=False,
                    redirect_uris="https://app.local/cb",
                    allowed_scopes="openid profile",
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()

            verifier = "v" * 64
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode("ascii")
            )
            code = oauth_server.issue_authorization_code(
                db,
                client_id=client_id,
                user_subject="l26-user",
                redirect_uri="https://app.local/cb",
                code_challenge=challenge,
            )
            first = oauth_server.exchange_code_for_tokens(
                db,
                client_id=client_id,
                code=code.code,
                redirect_uri="https://app.local/cb",
                code_verifier=verifier,
            )
            # First refresh succeeds + rotates.
            second = oauth_server.refresh_access_token(
                db,
                client_id=client_id,
                refresh_token=first["refresh_token"],
            )
            assert second["refresh_token"] != first["refresh_token"]

            # Second use of the ORIGINAL refresh token must fail
            # (single-use rotation; L26 long-session theft replay guard).
            with pytest.raises(oauth_server.OAuthError) as exc:
                oauth_server.refresh_access_token(
                    db,
                    client_id=client_id,
                    refresh_token=first["refresh_token"],
                )
            assert exc.value.code == "invalid_grant"
