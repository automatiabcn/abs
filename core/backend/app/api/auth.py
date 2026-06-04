# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Panel admin auth — JWT HTTP-only cookie oturumu.

CJ-007: setup wizard'dan yazilan /app/data/admin_credentials.json (email +
bcrypt hash) login akisinin kaynagidir. Dosya yoksa bootstrap fallback
(env'den admin_password_bootstrap + admin@local) calisir; bu sayede ilk-acilis
ve setup-sonrasi yollarin ikisi de tek endpoint'ten cozulur.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import bcrypt
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel, Field

from app.config import settings
from app.middleware.rate_limit import limiter
from app.observability.audit import emit_event  # Q12-L23

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


# Sprint 2I UAT-041 — per-email exponential backoff thresholds. Lockout
# kicks in once attempts cross _LOCKOUT_THRESHOLD; the delay doubles each
# subsequent attempt up to _LOCKOUT_MAX_SECONDS, then plateaus.
_LOCKOUT_THRESHOLD = 5
_LOCKOUT_BASE_SECONDS = 30
_LOCKOUT_MAX_SECONDS = 3600


def _backoff_seconds(attempts: int) -> int:
    """Return the seconds the email should remain locked after ``attempts``
    consecutive failures."""
    if attempts < _LOCKOUT_THRESHOLD:
        return 0
    delay = _LOCKOUT_BASE_SECONDS * (2 ** (attempts - _LOCKOUT_THRESHOLD))
    return min(delay, _LOCKOUT_MAX_SECONDS)


def _check_locked(email: str) -> Optional[datetime]:
    """Return the active ``locked_until`` value if ``email`` is still in
    backoff, otherwise None."""
    try:
        from sqlmodel import Session, select

        from app.db.models import FailedLoginAttempt
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            row = db.execute(
                select(FailedLoginAttempt).where(
                    FailedLoginAttempt.email == email
                )
            ).scalars().first()
            if row is None or row.locked_until is None:
                return None
            locked = row.locked_until
            if locked.tzinfo is None:
                locked = locked.replace(tzinfo=timezone.utc)
            if locked > datetime.now(timezone.utc):
                return locked
            return None
    except Exception as exc:
        logger.debug("failed_login lock check skipped (non-fatal): %s", exc)
        return None


def _record_failed_login(email: str, tenant_slug: Optional[str]) -> None:
    """Increment ``attempts_count`` and extend ``locked_until`` per the
    exponential backoff schedule."""
    try:
        from sqlmodel import Session, select

        from app.db.models import FailedLoginAttempt
        from app.db.session import get_engine

        now = datetime.now(timezone.utc)
        with Session(get_engine()) as db:
            row = db.execute(
                select(FailedLoginAttempt).where(
                    FailedLoginAttempt.email == email
                )
            ).scalars().first()
            if row is None:
                row = FailedLoginAttempt(
                    email=email,
                    tenant_slug=tenant_slug,
                    attempts_count=1,
                    last_attempt_at=now,
                    locked_until=None,
                )
            else:
                row.attempts_count = int(row.attempts_count or 0) + 1
                row.last_attempt_at = now
                if tenant_slug:
                    row.tenant_slug = tenant_slug
            backoff = _backoff_seconds(row.attempts_count)
            if backoff > 0:
                row.locked_until = now + timedelta(seconds=backoff)
            db.add(row)
            db.commit()
    except Exception as exc:
        logger.debug("failed_login record skipped (non-fatal): %s", exc)


def _clear_failed_login(email: str) -> None:
    """Drop the failed-login row on a successful authentication."""
    try:
        from sqlmodel import Session, delete

        from app.db.models import FailedLoginAttempt
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            db.execute(
                delete(FailedLoginAttempt).where(
                    FailedLoginAttempt.email == email
                )
            )
            db.commit()
    except Exception as exc:
        logger.debug("failed_login clear skipped (non-fatal): %s", exc)


def _hash_password(raw: str) -> bytes:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt())


def _verify_password(raw: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed)
    except (ValueError, TypeError):
        return False


BOOTSTRAP_ADMIN_EMAIL: str = "admin@local"
COOKIE_NAME = "abs_session"
COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 gün


def _admin_credentials_path() -> Path:
    return Path(settings.data_dir) / "admin_credentials.json"


def _load_admin_credentials_raw() -> Optional[Dict]:
    """Round-5 BUG-10 — read admin_credentials.json as a raw dict so callers
    that need fields beyond `(email, hash, source)` (e.g. ``tenant_slug``)
    can access them without breaking the legacy 3-tuple contract.

    Returns None when the file is missing or unreadable.
    """
    creds_file = _admin_credentials_path()
    try:
        raw = json.loads(creds_file.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "admin_credentials.json unreadable, falling back to bootstrap: %s", exc
        )
    return None


def _load_admin_credentials() -> Tuple[str, bytes, str]:
    """Setup wizard creds varsa onlari, yoksa bootstrap fallback dondur.

    Returns:
        (email, password_hash_bytes, source) — source bir teshis amacli string.
    """
    raw = _load_admin_credentials_raw()
    if raw is not None:
        try:
            return (
                raw["email"],
                raw["password_hash"].encode("utf-8"),
                "setup_wizard",
            )
        except KeyError as exc:
            logger.warning(
                "admin_credentials.json missing key, falling back to bootstrap: %s",
                exc,
            )

    bootstrap_hash = _hash_password(settings.admin_password_bootstrap)
    return BOOTSTRAP_ADMIN_EMAIL, bootstrap_hash, "bootstrap"


_TENANT_SLUG_RE = __import__("re").compile(r"^[a-z0-9](?:[a-z0-9\-]{0,30}[a-z0-9])?$")


def _derive_tenant_from_email(email: Optional[str]) -> Optional[str]:
    """Round-5 BUG-10 fallback — derive tenant_slug from the email domain's
    first label when no explicit slug is recorded.

    ``admin@demo-acme.com`` → ``demo-acme``. Single-label domains
    (``admin@local``, ``admin``) and slugs that fail the public signup
    regex return None so the resolver can fall through to ``default``
    instead of accepting an unsafe slug.
    """
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].lower()
    if "." not in domain:
        return None
    label = domain.split(".", 1)[0]
    if not _TENANT_SLUG_RE.match(label):
        return None
    return label


def _lookup_tenant_slug(email: str) -> Optional[str]:
    """Round-5 BUG-10 — resolve a session's tenant_slug from any source so
    the JWT mint can carry it as a claim.

    Order:
      1. ``users`` table (active row owns the truth when present).
      2. ``admin_credentials.json`` ``tenant_slug`` field (set by magic-link
         claim path, optionally by setup wizard).
      3. Email-domain heuristic for bootstrap-only deployments where neither
         source carries a slug yet.
    """
    if not email:
        return None
    try:
        from sqlmodel import Session, select

        from app.db.models import User
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            stmt = (
                select(User)
                .where(User.email == email)
                .where(User.status == "active")
            )
            user = db.execute(stmt).scalars().first()
            if user is not None and user.tenant_slug:
                return str(user.tenant_slug)
    except Exception as exc:
        logger.debug("tenant_slug DB lookup failed (non-fatal): %s", exc)

    raw = _load_admin_credentials_raw()
    if raw is not None and raw.get("email") == email:
        slug = raw.get("tenant_slug")
        if slug:
            return str(slug)

    return _derive_tenant_from_email(email)


def _lookup_user_in_db(email: str) -> Optional[Tuple[str, bytes, str]]:
    """Q4 P10 — multi-row login: query the `users` table first.

    Returns the same `(email, password_hash, source)` tuple as
    `_load_admin_credentials` so the login handler can treat both paths
    uniformly. Only `status == 'active'` rows are honoured (pending /
    revoked rows must not authenticate).

    Returns None when the table is empty, not yet migrated, or no active
    row matches the email.
    """
    try:
        from sqlmodel import Session, select

        from app.db.models import User
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            stmt = (
                select(User)
                .where(User.email == email)
                .where(User.status == "active")
            )
            user = db.execute(stmt).scalars().first()
            if user is None:
                return None
            return (
                user.email,
                user.password_hash.encode("utf-8"),
                "users_table",
            )
    except Exception as exc:
        logger.debug("user table lookup failed (non-fatal): %s", exc)
        return None


# Geriye-uyumluluk: bazi testler / modul tuketicileri ADMIN_EMAIL referansi
# kullaniyor olabilir. Bootstrap email'ini referans olarak yayinla.
ADMIN_EMAIL: str = BOOTSTRAP_ADMIN_EMAIL


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


def _create_token(email: str, tenant: Optional[str] = None) -> str:
    """Round-5 BUG-10 — embed an optional ``tenant`` claim alongside ``sub``.

    Without the claim, downstream tenant-scoped resolvers (e.g.
    ``marketplace._resolve_admin_tenant``) had to fall back to the bootstrap
    ``"default"`` slug whenever the users-table row was missing — true for
    every setup-wizard admin. Embedding the claim here closes that gap for
    the login + magic-link mint paths.
    """
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, object] = {
        "sub": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=COOKIE_MAX_AGE_SECONDS)).timestamp()),
    }
    if tenant:
        payload["tenant"] = tenant
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


class _SessionExpired(HTTPException):
    """Q12-L26 — typed exception so audit emission can read the reason
    without inspecting the (potentially i18n-translated) detail string.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum süresi doldu",
        )


class _SessionInvalid(HTTPException):
    """Q12-L26 — typed exception (signature mismatch, malformed JWT,
    tampered payload). Distinct from _SessionExpired so the audit
    `reason` stays accurate even if the i18n string drifts.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid",
        )


def _decode_token(token: str) -> Dict:
    try:
        return jwt.decode(token, settings.session_secret, algorithms=["HS256"])
    except ExpiredSignatureError as exc:
        raise _SessionExpired() from exc
    except JWTError as exc:
        raise _SessionInvalid() from exc


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="strict",
        secure=(settings.env == "prod"),
        path="/",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def current_admin(request: Request) -> Dict:
    """FastAPI dependency — protected route'larda kullanın."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        emit_event(
            request,
            action="auth.session.check",
            outcome="denied",
            reason="missing_cookie",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum yok"
        )
    try:
        return _decode_token(token)
    except _SessionExpired:
        emit_event(
            request,
            action="auth.session.decode",
            outcome="denied",
            reason="expired",
            status_code=401,
        )
        raise
    except _SessionInvalid:
        emit_event(
            request,
            action="auth.session.decode",
            outcome="denied",
            reason="invalid",
            status_code=401,
        )
        raise


@router.post("/login")
@limiter.limit("5/minute")
def login(payload: LoginRequest, request: Request, response: Response) -> Dict:
    """E-posta + parola ile oturum aç; JWT cookie set edilir.

    Q5.CO1 — multi-source verification: gather every (email, hash, source)
    candidate where the email matches the request, then accept the first
    candidate whose stored hash matches the submitted password. This lets
    `users` table rows and `admin_credentials.json` rows for the same email
    coexist (e.g. when the setup wizard rewrites the file but a DB row from
    an older magic-link claim still carries a stale hash). Only one source
    is needed to authenticate.

    Sprint 2I UAT-041 — `@limiter.limit("5/minute")` caps IP fan-out brute
    force, ``FailedLoginAttempt`` enforces per-email exponential backoff.
    """
    bad = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="E-posta veya parola hatalı",
    )

    locked_until = _check_locked(payload.email)
    if locked_until is not None:
        retry_after = max(
            1, int((locked_until - datetime.now(timezone.utc)).total_seconds())
        )
        emit_event(
            request,
            action="auth.login",
            outcome="denied",
            reason="email_locked",
            retry_after=retry_after,
            email_hint=(payload.email[:3] + "***") if payload.email else None,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Çok fazla başarısız deneme, lütfen bekleyin",
            headers={"Retry-After": str(retry_after)},
        )

    candidates: list[Tuple[str, bytes, str]] = []

    # Source 1 — `users` table (Q4 P10 DB-first).
    db_match = _lookup_user_in_db(payload.email)
    if db_match is not None and db_match[0] == payload.email:
        candidates.append(db_match)

    # Source 2 — `admin_credentials.json` (CJ-007 setup wizard / claim).
    file_match = _load_admin_credentials()
    if file_match[0] == payload.email:
        candidates.append(file_match)

    if not candidates:
        logger.info(
            "login_failed reason=email_no_source email=%s", payload.email
        )
        _record_failed_login(payload.email, None)
        emit_event(
            request,
            action="auth.login",
            outcome="denied",
            reason="email_no_source",
            email_hint=(payload.email[:3] + "***") if payload.email else None,
        )
        raise bad

    for admin_email, admin_hash, source in candidates:
        if _verify_password(payload.password, admin_hash):
            tenant_slug = _lookup_tenant_slug(admin_email)
            token = _create_token(admin_email, tenant=tenant_slug)
            _set_cookie(response, token)
            _clear_failed_login(admin_email)
            emit_event(
                request,
                action="auth.login",
                outcome="success",
                provider=source,
                email_hint=(admin_email[:3] + "***") if admin_email else None,
                tenant=tenant_slug or "",
            )
            return {
                "status": "logged_in",
                "email": admin_email,
                "source": source,
                "tenant_slug": tenant_slug,
            }

    logger.info(
        "login_failed reason=password_mismatch sources=%s",
        [c[2] for c in candidates],
    )
    _record_failed_login(
        payload.email, _lookup_tenant_slug(payload.email)
    )
    emit_event(
        request,
        action="auth.login",
        outcome="denied",
        reason="password_mismatch",
        count=len(candidates),
        email_hint=(payload.email[:3] + "***") if payload.email else None,
    )
    raise bad


@router.post("/logout")
def logout(response: Response) -> Dict:
    _clear_cookie(response)
    return {"status": "logged_out"}


# CJ-003 — public self-signup. Magic-link akisini /auth/signup tetikler.
class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    tenant_slug: str = Field(
        ..., min_length=2, max_length=32, pattern=r"^[a-z0-9](?:[a-z0-9\-]{0,30}[a-z0-9])?$"
    )
    # Q3 P2 — optional at signup; if provided, hashed and stored on the
    # pending User row so the claim step can promote without a second
    # password-set round-trip.
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


_SIGNUP_PENDING_FILE = "tenants_pending.json"


def _pending_signups_path() -> Path:
    return Path(settings.data_dir) / _SIGNUP_PENDING_FILE


def _read_pending_signups() -> list[dict]:
    p = _pending_signups_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write_pending_signups(rows: list[dict]) -> None:
    p = _pending_signups_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )


_MAGIC_TTL_SECONDS = 24 * 60 * 60  # Q3 P2 — 24h claim window


def _persist_user_pending(
    email: str, tenant_slug: str, password: Optional[str], magic_token: str
) -> None:
    """Q3 P2 — also write a `users` row alongside the JSON file so the
    multi-admin DB-backed lookup has a record. Best-effort: silent fail if
    the table doesn't exist yet (alembic 0006 not applied)."""
    try:
        from sqlmodel import Session, select

        from app.db.models import User
        from app.db.session import get_engine

        password_hash = (
            _hash_password(password).decode("utf-8")
            if password
            else _hash_password(secrets.token_urlsafe(16)).decode("utf-8")
        )
        expires = datetime.now(timezone.utc) + timedelta(
            seconds=_MAGIC_TTL_SECONDS
        )
        with Session(get_engine()) as db:
            stmt = select(User).where(User.email == email)
            existing = db.execute(stmt).scalars().first()
            if existing is not None:
                existing.password_hash = password_hash
                existing.tenant_slug = tenant_slug
                existing.magic_token = magic_token
                existing.magic_expires_at = expires
                existing.status = "pending"
                db.add(existing)
            else:
                db.add(
                    User(
                        email=email,
                        password_hash=password_hash,
                        tenant_slug=tenant_slug,
                        # Security: public self-signup must NOT mint an admin.
                        # admin_required now treats an active role=="admin"
                        # users row as a real console admin (multi-admin), so a
                        # hard-coded "admin" here would let anyone who can reach
                        # /auth/signup self-escalate. The bootstrap admin (setup
                        # wizard) or an explicit admin INVITE are the only paths
                        # to the admin role.
                        role="member",
                        status="pending",
                        magic_token=magic_token,
                        magic_expires_at=expires,
                    )
                )
            db.commit()
    except Exception as exc:
        logger.debug("user pending write failed (non-fatal): %s", exc)


def _claim_user_by_token(magic_token: str) -> Optional[Dict]:
    """Q3 P2 — find pending user by token, promote to active, mirror to
    admin_credentials.json so panel session login keeps working."""
    try:
        from sqlmodel import Session, select

        from app.db.models import User
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            stmt = select(User).where(User.magic_token == magic_token)
            user = db.execute(stmt).scalars().first()
            if user is None:
                return None
            # SQLite drops timezone on round-trip, so compare in naive UTC.
            now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            stored = user.magic_expires_at
            if stored is not None:
                stored_naive = (
                    stored.replace(tzinfo=None) if stored.tzinfo else stored
                )
                if stored_naive < now_naive:
                    return {"error": "expired"}
            user.status = "active"
            user.claimed_at = datetime.now(timezone.utc)
            user.magic_token = None
            db.add(user)
            db.commit()

            # Round-6 BUG-12 — only refresh admin_credentials.json when the
            # claimed user IS the bootstrap admin already recorded there.
            # Unconditional write let any /auth/signup → magic-claim flow
            # overwrite the setup-wizard bootstrap admin (lockout vector).
            # New admins live in the User table; the panel session cookie
            # set by this handler is enough — the JSON file is the
            # bootstrap-admin overlay only.
            existing = _load_admin_credentials_raw() or {}
            if existing.get("email") == user.email:
                _admin_credentials_path().write_text(
                    json.dumps(
                        {
                            "email": user.email,
                            "password_hash": user.password_hash,
                            "created_at": time.time(),
                            "tenant_slug": user.tenant_slug,
                            "source": "magic_link_claim",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            return {
                "email": user.email,
                "tenant_slug": user.tenant_slug,
                "role": user.role,
            }
    except Exception as exc:
        logger.warning("claim flow failed: %s", exc)
        return None


@router.post("/signup", status_code=201)
def signup(body: SignupRequest) -> Dict:
    """Self-host kurulumlarinda public self-signup. Magic-link log + pending tenant kaydi.

    Gercek e-posta gonderimi 011 (Stripe) + 023 (i18n) entegrasyonlarina bagli.
    Bu endpoint magic_token uretip JSON + DB'ye yazar; SMTP/transactional
    mailer kayitliysa hooks/event-bus uzerinden tetikler.
    """
    token = secrets.token_urlsafe(32)
    rows = _read_pending_signups()
    rows = [r for r in rows if r.get("email") != body.email]
    rows.append(
        {
            "email": body.email,
            "tenant_slug": body.tenant_slug,
            "magic_token": token,
            "created_at": time.time(),
            "expires_at": time.time() + _MAGIC_TTL_SECONDS,
        }
    )
    _write_pending_signups(rows)
    _persist_user_pending(body.email, body.tenant_slug, body.password, token)
    # Q12-L24-001 fix — never log the full magic token. It grants admin
    # session within 24h to anyone with log read access (ops, log
    # aggregator, accidental disclosure). Only a 6-char hint is logged so
    # ops can correlate signup → claim attempts without compromising the
    # claim flow.
    logger.info(
        "signup_pending email=%s slug=%s token_hint=%s***",
        body.email,
        body.tenant_slug,
        token[:6],
    )
    # Honesty fix — self-signup does NOT dispatch its own email. The previous
    # hard-coded `magic_link_sent: True` / `check_email: True` told the user a
    # mail was on the way that never came (no sender call here, and SMTP is
    # unset by default on self-host). Activation is delivered by an admin
    # invite (panel → copy link, or the invite email when SMTP is configured),
    # so we report the truth and point the user at that path.
    email_configured = bool(settings.smtp_host)
    response: Dict = {
        "status": "pending",
        "magic_link_sent": False,
        "email_configured": email_configured,
        "check_email": False,
        "tenant_slug": body.tenant_slug,
        "activation_note": (
            "Kaydınız alındı (beklemede). Hesabınızı etkinleştirmek için "
            "yöneticinizden sizi panelden davet etmesini veya aktivasyon "
            "bağlantısını paylaşmasını isteyin."
        ),
    }
    # Sprint 2I UAT-045 — production never echoes the magic_link in the
    # response body (access logs + APM trace storage retain it for 24h
    # which equals a working credential). Dev / test (env != "prod")
    # keep it so the existing harness can claim without an SMTP capture.
    if settings.env != "prod":
        response["magic_link"] = f"/activate?token={token}"
    return response


def _claim_invite_by_token(token: str) -> Optional[Dict]:
    """Sprint 2B BUG-36 — accept the magic-link plaintext, look up the
    matching ``tenant_invites`` row by HMAC digest, validate purpose +
    expiry + status, mark accepted, and return the user payload the
    panel session cookie will be minted from.
    """
    try:
        from sqlmodel import Session, select

        from app.auth.magic_link import hash_magic_token
        from app.db.models import TenantInvite, User
        from app.db.session import get_engine

        digest = hash_magic_token(token)
        with Session(get_engine()) as db:
            stmt = select(TenantInvite).where(
                TenantInvite.magic_token_hash == digest
            )
            invite = db.execute(stmt).scalars().first()
            if invite is None:
                return None
            if invite.status == "revoked":
                return {"error": "revoked"}
            if invite.status == "accepted":
                return {"error": "already_accepted"}
            stored = invite.expires_at
            now = datetime.now(timezone.utc)
            if stored is not None:
                exp = (
                    stored
                    if stored.tzinfo
                    else stored.replace(tzinfo=timezone.utc)
                )
                if exp < now:
                    return {"error": "expired"}
            invite.status = "accepted"
            invite.accepted_at = now
            db.add(invite)

            ustmt = select(User).where(User.email == invite.email)
            existing_user = db.execute(ustmt).scalars().first()
            if existing_user is None:
                user = User(
                    email=invite.email,
                    password_hash="",
                    tenant_slug=invite.tenant_id,
                    role=invite.role,
                    status="active",
                    magic_token=None,
                    magic_expires_at=None,
                    claimed_at=now,
                )
                db.add(user)
            else:
                existing_user.status = "active"
                existing_user.claimed_at = now
                existing_user.tenant_slug = invite.tenant_id
                existing_user.role = invite.role
                db.add(existing_user)
            db.commit()

            return {
                "email": invite.email,
                "tenant_slug": invite.tenant_id,
                "role": invite.role,
            }
    except Exception as exc:
        logger.warning("invite claim flow failed: %s", exc)
        return None


@router.get("/magic")
def magic_claim(token: str, request: Request, response: Response) -> Dict:
    """Q3 P2 — claim a pending signup. Sets the panel session cookie so the
    next /auth/login is unnecessary; user lands authenticated.

    Sprint 2B BUG-36 — also accepts admin-invite tokens minted by
    ``POST /v1/admin/users/invite``; the invite row carries an HMAC
    digest of the same plaintext so we can look it up here.

    Returns 200 with claim payload (frontend renders confirmation +
    optional redirect). Invalid token → 404; expired → 410."""
    if not token or len(token) < 16:
        emit_event(
            request,
            action="auth.magic.claim",
            outcome="denied",
            reason="invalid_token",
        )
        raise HTTPException(400, "invalid_token")

    invite_result = _claim_invite_by_token(token)
    if invite_result is not None:
        if invite_result.get("error") == "expired":
            emit_event(
                request,
                action="auth.magic.claim",
                outcome="denied",
                reason="invite_expired",
            )
            raise HTTPException(410, "token_expired")
        if invite_result.get("error") in ("revoked", "already_accepted"):
            emit_event(
                request,
                action="auth.magic.claim",
                outcome="denied",
                reason=f"invite_{invite_result['error']}",
            )
            raise HTTPException(410, f"invite_{invite_result['error']}")
        session_token = _create_token(
            invite_result["email"], tenant=invite_result.get("tenant_slug")
        )
        _set_cookie(response, session_token)
        emit_event(
            request,
            action="auth.magic.claim",
            outcome="success",
            reason="invite_accepted",
            tenant_id=invite_result.get("tenant_slug"),
        )
        return {
            "status": "claimed",
            "email": invite_result["email"],
            "tenant_slug": invite_result["tenant_slug"],
            "role": invite_result.get("role", "member"),
            "via": "invite",
        }

    result = _claim_user_by_token(token)
    if result is None:
        emit_event(
            request,
            action="auth.magic.claim",
            outcome="denied",
            reason="token_not_found",
        )
        raise HTTPException(404, "token_not_found")
    if result.get("error") == "expired":
        emit_event(
            request,
            action="auth.magic.claim",
            outcome="denied",
            reason="token_expired",
        )
        raise HTTPException(410, "token_expired")
    # Promote pending JSON row too (clean up).
    rows = _read_pending_signups()
    rows = [r for r in rows if r.get("magic_token") != token]
    _write_pending_signups(rows)

    session_token = _create_token(
        result["email"], tenant=result.get("tenant_slug")
    )
    _set_cookie(response, session_token)
    return {
        "status": "claimed",
        "email": result["email"],
        "tenant_slug": result["tenant_slug"],
        "role": result.get("role", "admin"),
    }


# /v1-prefixed alias for the SPA claim page. The frontend claim page lives at
# /activate (NOT /auth/magic) because Caddy routes /auth/* straight to the
# backend, which would otherwise hide the friendly page and show raw JSON. The
# page claims through this /v1 path so the Next.js rewrite (/v1/:path*) AND the
# Caddy backend route both reach the backend without colliding with any page.
claim_v1_router = APIRouter(prefix="/v1/auth", tags=["auth"])


@claim_v1_router.get("/magic-claim")
def magic_claim_v1(token: str, request: Request, response: Response) -> Dict:
    """Identical to GET /auth/magic; exposed under /v1 for the /activate page."""
    return magic_claim(token, request, response)


@router.get("/me")
def me(request: Request) -> Dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        emit_event(
            request,
            action="auth.me.check",
            outcome="denied",
            reason="missing_cookie",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum yok"
        )
    # Q12-L26 — emit audit on decode failure (expired vs invalid).
    try:
        payload = _decode_token(token)
    except _SessionExpired:
        emit_event(
            request,
            action="auth.session.decode",
            outcome="denied",
            reason="expired",
            status_code=401,
        )
        raise
    except _SessionInvalid:
        emit_event(
            request,
            action="auth.session.decode",
            outcome="denied",
            reason="invalid",
            status_code=401,
        )
        raise
    exp = payload.get("exp")
    exp_iso = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else ""
    )
    return {"email": payload.get("sub", ""), "exp_at": exp_iso}
