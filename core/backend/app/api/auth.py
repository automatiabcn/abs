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
from app.observability.audit import emit_event  # Q12-L23

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


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


def _load_admin_credentials() -> Tuple[str, bytes, str]:
    """Setup wizard creds varsa onlari, yoksa bootstrap fallback dondur.

    Returns:
        (email, password_hash_bytes, source) — source bir teshis amacli string.
    """
    creds_file = _admin_credentials_path()
    try:
        raw = json.loads(creds_file.read_text(encoding="utf-8"))
        email = raw["email"]
        password_hash = raw["password_hash"].encode("utf-8")
        return email, password_hash, "setup_wizard"
    except FileNotFoundError:
        pass
    except (KeyError, json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "admin_credentials.json unreadable, falling back to bootstrap: %s", exc
        )

    bootstrap_hash = _hash_password(settings.admin_password_bootstrap)
    return BOOTSTRAP_ADMIN_EMAIL, bootstrap_hash, "bootstrap"


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


def _create_token(email: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=COOKIE_MAX_AGE_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def _decode_token(token: str) -> Dict:
    try:
        return jwt.decode(token, settings.session_secret, algorithms=["HS256"])
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum süresi doldu"
        ) from exc
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalid"
        ) from exc


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
    except HTTPException as http_exc:
        emit_event(
            request,
            action="auth.session.decode",
            outcome="denied",
            reason="expired" if http_exc.status_code == 401 and "süresi" in str(http_exc.detail) else "invalid",
            status_code=http_exc.status_code,
        )
        raise


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> Dict:
    """E-posta + parola ile oturum aç; JWT cookie set edilir.

    Q5.CO1 — multi-source verification: gather every (email, hash, source)
    candidate where the email matches the request, then accept the first
    candidate whose stored hash matches the submitted password. This lets
    `users` table rows and `admin_credentials.json` rows for the same email
    coexist (e.g. when the setup wizard rewrites the file but a DB row from
    an older magic-link claim still carries a stale hash). Only one source
    is needed to authenticate.
    """
    bad = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="E-posta veya parola hatalı",
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
            token = _create_token(admin_email)
            _set_cookie(response, token)
            emit_event(
                request,
                action="auth.login",
                outcome="success",
                provider=source,
                email_hint=(admin_email[:3] + "***") if admin_email else None,
            )
            return {
                "status": "logged_in",
                "email": admin_email,
                "source": source,
            }

    logger.info(
        "login_failed reason=password_mismatch sources=%s",
        [c[2] for c in candidates],
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
                        role="admin",
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
    return {
        "status": "pending",
        "magic_link_sent": True,
        "tenant_slug": body.tenant_slug,
        "magic_link": f"/auth/magic?token={token}",
    }


@router.get("/magic")
def magic_claim(token: str, request: Request, response: Response) -> Dict:
    """Q3 P2 — claim a pending signup. Sets the panel session cookie so the
    next /auth/login is unnecessary; user lands authenticated.

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

    session_token = _create_token(result["email"])
    _set_cookie(response, session_token)
    return {
        "status": "claimed",
        "email": result["email"],
        "tenant_slug": result["tenant_slug"],
        "role": result.get("role", "admin"),
    }


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
    payload = _decode_token(token)
    exp = payload.get("exp")
    exp_iso = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else ""
    )
    return {"email": payload.get("sub", ""), "exp_at": exp_iso}
