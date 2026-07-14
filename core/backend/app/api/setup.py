# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Setup wizard — a 6-step state machine and its endpoints.

State file: <data_dir>/setup_state.json
Steps:
  1) admin     {email, password}
  2) license   {license_key}  — optional; empty means the free tier
  3) domain    {mode, domain?, ssl_mode}
  4) anthropic {anthropic_api_key} — optional
  5) providers {groq_api_key?, gemini_api_key?, ...} — all optional
  6) test      {} → a server-side ping of every configured provider

When the wizard finishes, `setup_state.completed=True`. The first-run middleware
reads that flag and redirects to /setup until it is set.
"""

from __future__ import annotations

import json
import logging
import re
import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.config import settings
from app.licensing import verify_license
from app.observability.audit import emit_event


def _persist_customer_audit(
    license_jti: str | None,
    action: str,
    detail: str | None = None,
) -> None:
    """Best-effort persistence to CustomerAuditEntry.

    `emit_event` ships structured logs but never writes to the DB, which
    is why the /v1/admin/audit/recent UI was perpetually empty after the
    setup wizard ran. Writing the same lifecycle events into the
    HMAC-chain audit table makes them surface in the admin viewer
    without changing the broader emit_event contract.

    Tolerates missing license_jti (pre-license setup steps fall back to
    the literal `setup-pre-license` so the row is still queryable).
    Failures are swallowed — audit must never block the wizard.
    """
    try:
        from sqlmodel import Session

        from app.db.models import CustomerAuditEntry
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            db.add(
                CustomerAuditEntry(
                    license_jti=(license_jti or "setup-pre-license")[:64],
                    action=action[:64],
                    detail=(detail or None) and detail[:512],
                )
            )
            db.commit()
    except Exception as exc:  # pragma: no cover — defensive only
        logger.info("customer_audit_persist_skipped action=%s err=%s", action, exc)


router = APIRouter(prefix="/v1/setup", tags=["setup"])
logger = logging.getLogger(__name__)


# ---------- helpers --------------------------------------------------------


def setup_state_path() -> Path:
    """Path to the setup state JSON (mkdir is best-effort)."""
    p = Path(settings.data_dir) / "setup_state.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Read-only filesystem (e.g. the module imported directly from the
        # Host in dev) — skip silently rather than fail the request.
        pass
    return p


def admin_credentials_path() -> Path:
    return Path(settings.data_dir) / "admin_credentials.json"


def _initial_state() -> Dict[str, Any]:
    return {
        "completed": False,
        "current_step": 1,
        "completed_steps": [],
        "started_at": time.time(),
        "completed_at": None,
        "lang": "en",  # preferred wizard language (en|tr|es)
        "data": {
            "admin": None,
            "license": None,
            "domain": None,
            "anthropic_configured": False,
            "providers_configured": [],
            "test_results": {},
        },
    }


def read_state() -> Dict[str, Any]:
    """Read the setup state, or return the initial state. Never writes."""
    p = setup_state_path()
    if not p.is_file():
        return _initial_state()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _initial_state()


def _atomic_write_state(state: Dict[str, Any]) -> None:
    target = setup_state_path()
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


# TOCTOU guard for setup wizard step endpoints.
#
# Pre-fix: each step handler did `read_state → mutate → _atomic_write_state`
# without serialization. Two concurrent admins (multi-worker uvicorn or
# event-loop interleaving on slow I/O) both read `current_step=N`, both
# pass `_ensure_step(state, N)`, both write to disk, last-writer-wins on
# `admin_credentials.json` and on the state file — silent overwrite.
#
# Post-fix: every step handler wraps `read_state ... _atomic_write_state`
# in `with _state_lock():`. fcntl.LOCK_EX on a companion .lock file
# serializes across threads AND processes (multi-worker safe). The
# losing concurrent call observes the already-advanced state on its read
# and returns 409 from `_ensure_step`.
import contextlib
import fcntl


def _state_lock_path() -> Path:
    return setup_state_path().with_suffix(".json.lock")


@contextlib.contextmanager
def _state_lock():
    """Acquire an exclusive cross-process lock on the setup state file.

    The lock file is auto-created on first use. fcntl.LOCK_EX blocks
    until the previous holder releases (no busy-wait, no deadlock as
    long as the holder doesn't fork mid-critical-section). Released
    automatically on file close.
    """
    p = _state_lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def _persist_encrypted_secret(vault_key: str, value: str) -> bool:
    """Writes to the sops vault, falling back to .env when no vault exists
    (dev/test).

    `vault_key` is snake_case (e.g. `anthropic_api_key`); the .env fallback
    converts it to `ABS_<UPPER>`.
    """
    try:
        from app.vault.audit import log_event
        from app.vault.runner import (
            VaultError,
            master_key_exists,
            sops_available,
            write_secret,
        )

        if sops_available() and master_key_exists():
            try:
                write_secret(vault_key, value)
                log_event("write", vault_key, source="setup_wizard")
                return True
            except VaultError as exc:
                logger.warning("vault write fail, falling back to .env: %s", exc)
    except Exception as exc:
        logger.info("vault unavailable, .env fallback: %s", exc)
    return _persist_env_var(f"ABS_{vault_key.upper()}", value)


def _persist_env_var(key: str, value: str, env_path: Optional[str] = None) -> bool:
    """Generic .env patcher. Returns False when the file is absent; persistence
    is not required in test/dev."""
    raw_path = env_path or settings.model_config.get("env_file") or ".env"
    env_file = Path(str(raw_path))
    if not env_file.is_file():
        return False
    lines = env_file.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    updated = False
    for idx, line in enumerate(lines):
        if line.startswith(prefix):
            lines[idx] = f"{prefix}{value}"
            updated = True
            break
    if not updated:
        lines.append(f"{prefix}{value}")
    with tempfile.NamedTemporaryFile(
        "w", delete=False, encoding="utf-8", dir=str(env_file.parent)
    ) as tmp:
        tmp.write("\n".join(lines) + "\n")
        tmp_path = Path(tmp.name)
    shutil.move(str(tmp_path), str(env_file))
    return True


def _ensure_step(
    state: Dict[str, Any],
    expected: int,
    request: Optional[Request] = None,
    step_key: Optional[str] = None,
) -> None:
    """Emit audit event before raising 409.

    Operators need to know which wizard step a stalled install hung on
    *before* they look at logs. Pre-fix, both branches raised silently
    and the only signal was a 409 in the access log with no step
    context, no current_step value, no actor (these endpoints have no
    auth yet — the fix-onset moment of the system).
    """
    if state.get("completed"):
        emit_event(
            request,
            action="setup.step.gate",
            outcome="denied",
            reason="setup_already_completed",
            resource_type=step_key or f"step_{expected}",
            status_code=409,
        )
        raise HTTPException(status_code=409, detail="Setup already completed")
    if state.get("current_step") != expected:
        emit_event(
            request,
            action="setup.step.gate",
            outcome="denied",
            reason="step_not_active",
            resource_type=step_key or f"step_{expected}",
            status_code=409,
            count=int(state.get("current_step") or 0),
        )
        raise HTTPException(
            status_code=409,
            detail=f"This step is not active (current_step={state.get('current_step')})",
        )


_STEP_NUMBERS = {
    "admin": 1,
    "license": 2,
    "domain": 3,
    "anthropic": 4,
    "providers": 5,
    "test": 6,
}


def _emit_funnel_step(state: Dict[str, Any], step_key: str) -> None:
    """extracted from _advance so the wizard-completion logic and the
    metric emission stay independently testable. Best-effort; metric errors
    must never block the wizard transition."""
    try:
        from app.wizard.metrics import record_step

        session_id = state.get("session_id") or state.get("started_at", "anon")
        step_num = _STEP_NUMBERS.get(step_key, 0)
        if step_num:
            record_step(str(session_id), step_num, completed=True)
    except Exception:
        pass


def _advance(state: Dict[str, Any], step_key: str) -> None:
    """Mark the step complete and advance current_step by one."""
    if step_key not in state["completed_steps"]:
        state["completed_steps"].append(step_key)
    if state["current_step"] < 6:
        state["current_step"] += 1
    _emit_funnel_step(state, step_key)


# ---------- step bodies ----------------------------------------------------


# RFC 6761 special-use TLDs, allowed so intranet self-host installs can use
# an admin address that no public MX would accept.
_RFC6761_LOCAL_TLDS = ("local", "test", "example", "invalid", "localhost")
_LOCAL_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.(" + "|".join(_RFC6761_LOCAL_TLDS) + r")$"
)


class AdminBody(BaseModel):
    email: str
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        # RFC 6761 special-use TLDs (.local / .test / .example / .invalid /
        # .localhost) are accepted during setup; .local is common on intranet
        # Deployments.
        if _LOCAL_EMAIL_RE.match(value):
            return value
        # Everything else goes through standard EmailStr validation.
        from pydantic import TypeAdapter

        return TypeAdapter(EmailStr).validate_python(value)


class LicenseBody(BaseModel):
    """The key is optional, because running ABS does not require one.

    It used to be `Field(..., min_length=10)`, which meant the wizard could not
    be finished without a license — on a product whose whole pitch is that the
    free tier is the default and good enough. The screen said "without a license,
    demo mode stays active for 14 days" directly above a field you could not leave
    empty. A customer with no key got as far as step 2 and stopped.
    """

    license_key: Optional[str] = Field(default=None, max_length=4096)


class DomainBody(BaseModel):
    mode: Literal["ip", "domain"] = "ip"
    domain: Optional[str] = None
    ssl_mode: Literal["internal", "acme"] = "internal"


_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class AnthropicBody(BaseModel):
    """Anthropic key opsiyonel: free-tier (skip_paid_providers=True)
    musterilerin Anthropic API key'i olmadan setup'i tamamlamasina izin verir.
    The key stays mandatory on the paid tier.
    """

    anthropic_api_key: Optional[str] = Field(default=None, min_length=8)
    skip_paid_providers: bool = False

    @model_validator(mode="after")
    def _validate_payload(self) -> "AnthropicBody":
        if self.skip_paid_providers:
            # Free tier: an Anthropic key is ignored even if one is sent.
            self.anthropic_api_key = None
            return self
        if not self.anthropic_api_key:
            raise ValueError("anthropic_api_key required for paid tier")
        if not _ANTHROPIC_RE.match(self.anthropic_api_key):
            raise ValueError("Anthropic API key formati gecersiz")
        return self


_ANTHROPIC_RE = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{4,}$")


class ProvidersBody(BaseModel):
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    cerebras_api_key: Optional[str] = None
    cohere_api_key: Optional[str] = None
    cf_account_id: Optional[str] = None
    cf_api_token: Optional[str] = None


# Offline format checks for the providers step. These catch the common
# self-serve mistakes — a key pasted into the wrong field, surrounding
# whitespace, or obviously-truncated text — BEFORE the key is stored and the
# operator only discovers it's wrong at runtime. groq/gemini have very stable
# prefixes (high-value cross-paste guard); cerebras keeps its prefix optional
# and the rest fall back to a charset+length sanity check so a real key is
# never falsely rejected. The step-6 live ping remains the source of truth.
_PROVIDER_KEY_RULES: Dict[str, "tuple[re.Pattern[str], str]"] = {
    "groq_api_key": (
        re.compile(r"^gsk_[A-Za-z0-9]{6,}$"),
        "Groq keys start with 'gsk_'",
    ),
    "gemini_api_key": (
        re.compile(r"^AIza[0-9A-Za-z_\-]{10,}$"),
        "Google/Gemini keys start with 'AIza'",
    ),
    "cerebras_api_key": (
        re.compile(r"^(csk-)?[A-Za-z0-9_\-]{16,}$"),
        "This does not look like a Cerebras key",
    ),
    "cohere_api_key": (
        re.compile(r"^[A-Za-z0-9_\-]{16,}$"),
        "Cohere keys are 16+ URL-safe characters",
    ),
    "cf_account_id": (
        re.compile(r"^[0-9a-fA-F]{32}$"),
        "A Cloudflare account ID is 32 hex characters",
    ),
    "cf_api_token": (
        re.compile(r"^[A-Za-z0-9_\-]{20,}$"),
        "This does not look like a Cloudflare API token",
    ),
}


# ---------- endpoints ------------------------------------------------------


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return read_state()


# Setup wizard language picker (overrides browser auto-detect)
class SetupLangBody(BaseModel):
    lang: str  # en|tr|es


@router.post("/lang", status_code=status.HTTP_200_OK)
async def set_setup_lang(body: SetupLangBody, request: Request) -> Dict[str, Any]:
    if body.lang not in ("en", "tr", "es"):
        emit_event(
            request,
            action="setup.lang.set",
            outcome="denied",
            reason="unsupported_language",
            status_code=400,
        )
        raise HTTPException(status_code=400, detail="Unsupported language")
    with _state_lock():
        state = read_state()
        state["lang"] = body.lang
        _atomic_write_state(state)
    emit_event(
        request,
        action="setup.lang.set",
        outcome="success",
        resource_type=body.lang,
    )
    return {"ok": True, "lang": body.lang}


def _assert_no_existing_admin(request: Request) -> None:
    """Refuse to (re)write admin credentials when an admin already exists.

    The wizard is intentionally unauthenticated — it is how the very first
    admin is created. Its only gate used to be `setup_state.completed`,
    which lives in a JSON file next to the DB. Anyone who could make that
    file disappear (a restore that misses it, a wiped data volume, an
    operator "resetting" the wizard) reopened step 1 to the whole network,
    and step 1 overwrites `admin_credentials.json` — a full panel takeover
    with no credentials required.

    The credentials file itself is the durable fact, so we gate on it: if
    an admin exists, step 1 is closed regardless of what the state file
    says. Recovering a lost admin password now requires host access
    (delete the credentials file), which is the correct trust boundary.
    """
    if not admin_credentials_path().is_file():
        return
    emit_event(
        request,
        action="setup.step.gate",
        outcome="denied",
        reason="admin_already_exists",
        resource_type="admin",
        status_code=409,
    )
    raise HTTPException(
        status_code=409,
        detail=(
            "An administrator already exists. Setup cannot re-create it. "
            "Sign in, or remove admin_credentials.json on the host to recover."
        ),
    )


@router.post("/step/admin", status_code=status.HTTP_200_OK)
async def step_admin(body: AdminBody, request: Request) -> Dict[str, Any]:
    with _state_lock():
        state = read_state()
        _assert_no_existing_admin(request)
        _ensure_step(state, 1, request, "admin")
        pwd_hash = bcrypt.hashpw(
            body.password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        admin_credentials_path().write_text(
            json.dumps(
                {
                    "email": body.email,
                    "password_hash": pwd_hash,
                    "created_at": time.time(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state["data"]["admin"] = {"email": body.email}
        _persist_env_var("ABS_ADMIN_EMAIL", body.email)
        _advance(state, "admin")
        _atomic_write_state(state)
    emit_event(
        request,
        action="setup.step.complete",
        outcome="success",
        resource_type="admin",
        email_hint=(body.email or "")[:3],
    )
    return {"ok": True, "current_step": state["current_step"]}


@router.post("/step/license", status_code=status.HTTP_200_OK)
async def step_license(body: LicenseBody, request: Request) -> Dict[str, Any]:
    with _state_lock():
        state = read_state()
        _ensure_step(state, 2, request, "license")

        key = (body.license_key or "").strip()
        if not key:
            # No key: the free tier. Start the demo clock and move on — this is a
            # supported way to run the product, not a failure to configure it.
            from app.licensing.demo import start_demo

            demo = start_demo()
            state["data"]["license"] = {
                "mode": "demo",
                "expires_at": demo.get("expires_at"),
            }
            _advance(state, "license")
            _atomic_write_state(state)
            emit_event(
                request,
                action="setup.step.complete",
                outcome="success",
                resource_type="license",
                detail="free_tier",
            )
            return {
                "ok": True,
                "current_step": state["current_step"],
                "tier": "free",
            }

        try:
            payload = verify_license(key)
        except HTTPException as exc:
            emit_event(
                request,
                action="setup.step.license",
                outcome="denied",
                reason="license_invalid",
                status_code=400,
                error_class="HTTPException",
            )
            raise HTTPException(
                status_code=400, detail=f"Invalid license: {exc.detail}"
            ) from exc

        settings.license_key = key
        _persist_encrypted_secret("license_key", key)
        state["data"]["license"] = {
            "jti": payload.get("jti"),
            "tier": payload.get("tier"),
            "seat_count": payload.get("seat_count"),
        }
        _advance(state, "license")
        _atomic_write_state(state)
    emit_event(
        request,
        action="setup.step.complete",
        outcome="success",
        resource_type="license",
        provider=str(payload.get("tier") or ""),
    )
    _persist_customer_audit(
        license_jti=str(payload.get("jti") or "") or None,
        action="setup.license.activated",
        detail=f"tier={payload.get('tier')} seats={payload.get('seat_count')}",
    )
    return {
        "ok": True,
        "current_step": state["current_step"],
        "tier": payload.get("tier"),
    }


@router.post("/step/domain", status_code=status.HTTP_200_OK)
async def step_domain(body: DomainBody, request: Request) -> Dict[str, Any]:
    with _state_lock():
        state = read_state()
        _ensure_step(state, 3, request, "domain")
        if body.mode == "domain":
            if not body.domain or not _DOMAIN_RE.match(body.domain):
                emit_event(
                    request,
                    action="setup.step.domain",
                    outcome="denied",
                    reason="domain_invalid",
                    status_code=400,
                )
                raise HTTPException(status_code=400, detail="Domain formati gecersiz")
            settings.domain = body.domain
            _persist_env_var("ABS_DOMAIN", body.domain)
        settings.ssl_mode = body.ssl_mode
        _persist_env_var("ABS_SSL_MODE", body.ssl_mode)
        state["data"]["domain"] = {
            "mode": body.mode,
            "domain": body.domain,
            "ssl_mode": body.ssl_mode,
        }
        _advance(state, "domain")
        _atomic_write_state(state)
    emit_event(
        request,
        action="setup.step.complete",
        outcome="success",
        resource_type="domain",
        provider=body.ssl_mode,
    )
    return {"ok": True, "current_step": state["current_step"]}


@router.post("/step/anthropic", status_code=status.HTTP_200_OK)
async def step_anthropic(body: AnthropicBody, request: Request) -> Dict[str, Any]:
    with _state_lock():
        state = read_state()
        _ensure_step(state, 4, request, "anthropic")
        if body.skip_paid_providers:
            # Free-tier flow: skip Anthropic, set the paid_skipped flag.
            state["data"]["anthropic_configured"] = False
            state["data"]["paid_skipped"] = True
        else:
            # Model_validator already checked format and required fields;
            # This only persists.
            assert body.anthropic_api_key is not None  # for type-checker
            settings.anthropic_api_key = body.anthropic_api_key
            _persist_encrypted_secret("anthropic_api_key", body.anthropic_api_key)
            # Vault stores the secret but pydantic Settings only re-reads
            # .env at boot, so an explicit env-var write is required for a clean
            # restart to surface the key. Vault path is the encrypted-at-rest
            # source of truth; .env is the boot-loader.
            _persist_env_var("ABS_ANTHROPIC_API_KEY", body.anthropic_api_key)
            # Settings.anthropic_enabled defaults to False so that an
            # operator who hasn't configured a key never silently calls the
            # paid provider. When the wizard accepts a valid key we must flip
            # the flag, otherwise the cascade router skips Anthropic forever.
            settings.anthropic_enabled = True
            _persist_env_var("ABS_ANTHROPIC_ENABLED", "true")
            state["data"]["anthropic_configured"] = True
            state["data"]["paid_skipped"] = False
        _advance(state, "anthropic")
        _atomic_write_state(state)
    emit_event(
        request,
        action="setup.step.complete",
        outcome="success",
        resource_type="anthropic",
        provider="skipped" if body.skip_paid_providers else "configured",
    )
    _persist_customer_audit(
        license_jti=str(state.get("data", {}).get("license", {}).get("jti") or "")
        or None,
        action="setup.provider.anthropic",
        detail="skipped" if body.skip_paid_providers else "configured",
    )
    return {
        "ok": True,
        "current_step": state["current_step"],
        "paid_skipped": state["data"].get("paid_skipped", False),
    }


@router.post("/step/providers", status_code=status.HTTP_200_OK)
async def step_providers(body: ProvidersBody, request: Request) -> Dict[str, Any]:
    with _state_lock():
        state = read_state()
        _ensure_step(state, 5, request, "providers")
        configured: list[str] = []
        provider_fields = (
            "groq_api_key",
            "gemini_api_key",
            "cerebras_api_key",
            "cohere_api_key",
            "cf_account_id",
            "cf_api_token",
        )
        # Validate format BEFORE persisting anything so a malformed key never
        # reaches the vault/.env (and the step stays atomic — all or nothing).
        key_errors: Dict[str, str] = {}
        for field_name in provider_fields:
            raw = getattr(body, field_name)
            if not raw or not str(raw).strip():
                continue
            value = str(raw).strip()
            rule = _PROVIDER_KEY_RULES.get(field_name)
            if rule and not rule[0].match(value):
                key_errors[field_name] = rule[1]
        if key_errors:
            emit_event(
                request,
                action="setup.step.providers",
                outcome="denied",
                reason="invalid_key_format",
                status_code=400,
            )
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_provider_key_format", "fields": key_errors},
            )
        for field_name in provider_fields:
            value = getattr(body, field_name)
            value = value.strip() if value else value
            if value:
                setattr(settings, field_name, value)
                _persist_encrypted_secret(field_name, value)
                # Same reason as the Anthropic step: pydantic Settings
                # reads .env once at boot, so the vault write alone is not
                # enough for the cascade router to pick up new keys after a
                # container restart.
                _persist_env_var(f"ABS_{field_name.upper()}", value)
                configured.append(field_name)
        state["data"]["providers_configured"] = configured
        _advance(state, "providers")
        _atomic_write_state(state)
    emit_event(
        request,
        action="setup.step.complete",
        outcome="success",
        resource_type="providers",
        count=len(configured),
    )
    _persist_customer_audit(
        license_jti=str(state.get("data", {}).get("license", {}).get("jti") or "")
        or None,
        action="setup.providers.configured",
        detail=",".join(configured) if configured else "none",
    )
    return {"ok": True, "current_step": state["current_step"], "configured": configured}


# Provider key field → cascade provider name. cf_account_id is not an
# independently pingable key (Cloudflare is validated via cf_api_token).
_FIELD_TO_PROVIDER: Dict[str, str] = {
    "groq_api_key": "groq",
    "gemini_api_key": "gemini",
    "cerebras_api_key": "cerebras",
    "cohere_api_key": "cohere",
    "anthropic_api_key": "anthropic",
    "cf_api_token": "cloudflare",
}


async def _run_provider_tests() -> Dict[str, Any]:
    """Adim 6 — ping each configured provider with the just-entered key so the
    operator sees IN the wizard whether their keys actually work (not later).

    A failed ping is recorded as ``fail`` but never blocks completion. Skipped
    under ``ABS_TEST_MODE=1`` (no network in tests) and for non-pingable fields,
    so the existing setup-wizard test suite stays deterministic.
    """
    results: Dict[str, Any] = {}
    state = read_state()
    configured = list(state.get("data", {}).get("providers_configured", []) or [])
    if state.get("data", {}).get("anthropic_configured"):
        configured = ["anthropic_api_key", *configured]

    live = os.environ.get("ABS_TEST_MODE") != "1"
    for field_name in configured:
        provider = _FIELD_TO_PROVIDER.get(field_name)
        if provider is None:
            results[field_name] = {"status": "skipped", "reason": "not a pingable key"}
            continue
        if not live:
            results[field_name] = {
                "status": "skipped",
                "reason": "live ping disabled in test mode",
            }
            continue
        try:
            from app.cascade.orchestrator import call_with_cascade

            resp = await asyncio.wait_for(
                call_with_cascade(
                    "ping", primary=provider, fallbacks=(), use_cache=False
                ),
                timeout=8.0,
            )
            ok = bool(getattr(resp, "text", ""))
            results[field_name] = (
                {"status": "ok", "provider": provider}
                if ok
                else {
                    "status": "fail",
                    "provider": provider,
                    "reason": "empty response",
                }
            )
        except Exception as exc:  # noqa: BLE001 — a failed ping must not block setup
            results[field_name] = {
                "status": "fail",
                "provider": provider,
                "reason": str(exc)[:160],
            }
    return results


@router.post("/step/test", status_code=status.HTTP_200_OK)
async def step_test(request: Request) -> Dict[str, Any]:
    with _state_lock():
        state = read_state()
        _ensure_step(state, 6, request, "test")
        test_results = await _run_provider_tests()
        state["data"]["test_results"] = test_results
        if "test" not in state["completed_steps"]:
            state["completed_steps"].append("test")
        state["completed"] = True
        state["completed_at"] = time.time()
        _atomic_write_state(state)
    emit_event(
        request,
        action="setup.wizard.completed",
        outcome="success",
        resource_type="setup_wizard",
        count=len(test_results),
    )
    return {
        "ok": True,
        "completed": True,
        "current_step": state["current_step"],
        "test_results": test_results,
    }


@router.post("/test", status_code=status.HTTP_200_OK)
async def dry_run_test(request: Request) -> Dict[str, Any]:
    """Ping every configured provider WITHOUT finishing the wizard.

    `/step/test` both tests and completes, in that order and irreversibly: once
    it has run, `_ensure_step` answers 409 to every earlier step. So the only
    way a customer could see whether their keys work was to first give up the
    ability to go back and fix them — and a wizard that says "your Groq key is
    wrong" on a screen you can no longer leave is worse than one that says
    nothing.

    This runs the same checks and writes nothing. Step 6 calls it on "Run the
    test", and only calls `/step/test` when the customer has read the verdict
    and chosen to finish.
    """
    state = read_state()
    if state.get("completed"):
        raise HTTPException(status_code=409, detail="Setup already completed")
    results = await _run_provider_tests()
    emit_event(
        request,
        action="setup.test.dry_run",
        outcome="success",
        resource_type="providers",
        count=len(results),
    )
    return {"ok": True, "test_results": results}


@router.post("/reset", status_code=status.HTTP_200_OK)
async def reset_setup(request: Request) -> Dict[str, Any]:
    """Dev-only — when `settings.env == 'dev'`, drop the setup state and the admin
    credentials so the wizard can be run again from scratch."""
    if settings.env != "dev":
        emit_event(
            request,
            action="setup.reset",
            outcome="denied",
            reason="non_dev_env",
            status_code=403,
            provider=settings.env or "unknown",
        )
        raise HTTPException(
            status_code=403, detail="Reset is only permitted in a dev environment"
        )
    p = setup_state_path()
    cred = admin_credentials_path()
    if p.is_file():
        p.unlink()
    if cred.is_file():
        cred.unlink()
    emit_event(
        request,
        action="setup.reset",
        outcome="success",
        resource_type="setup_state",
    )
    return {"ok": True, "reset": True}
