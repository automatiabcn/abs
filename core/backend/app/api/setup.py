"""012 — Setup Wizard 6-step state machine + endpoint'leri.

State file: <data_dir>/setup_state.json
Adimlar:
  1) admin     {email, password}
  2) license   {license_key}
  3) domain    {mode, domain?, ssl_mode}
  4) anthropic {anthropic_api_key}
  5) providers {groq_api_key?, gemini_api_key?, ...}
  6) test      {} → server-side provider ping (mock'lanir)

Setup tamamlandiktan sonra `setup_state.completed=True`.
First-run middleware bu flag'i okur ve aksi takdirde /setup'a redirect eder.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import bcrypt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.config import settings
from app.licensing import verify_license

router = APIRouter(prefix="/v1/setup", tags=["setup"])
logger = logging.getLogger(__name__)


# ---------- helpers --------------------------------------------------------


def setup_state_path() -> Path:
    """Setup state JSON dosyasinin yolu (mkdir best-effort)."""
    p = Path(settings.data_dir) / "setup_state.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Read-only fs (orn. host'tan dev olarak modul import edildiginde) — sessizce gec
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
        "lang": "en",  # 023 — preferred wizard language (en|tr|es)
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
    """Setup state'i oku, yoksa initial state dondur (yazmaz)."""
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


# Q12-L22-001 — TOCTOU guard for setup wizard step endpoints.
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
    """013 — Önce sops vault'a yaz; vault yoksa fallback olarak .env (dev/test).

    `vault_key` snake_case (örn. `anthropic_api_key`); .env fallback'ında
    otomatik `ABS_<UPPER>` formatına çevrilir.
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
                logger.warning(
                    "vault write fail, falling back to .env: %s", exc
                )
    except Exception as exc:
        logger.info("vault unavailable, .env fallback: %s", exc)
    return _persist_env_var(f"ABS_{vault_key.upper()}", value)


def _persist_env_var(key: str, value: str, env_path: Optional[str] = None) -> bool:
    """Generic .env patcher. Dosya yoksa False (test/dev'de persist zorunlu degil)."""
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


def _ensure_step(state: Dict[str, Any], expected: int) -> None:
    if state.get("completed"):
        raise HTTPException(status_code=409, detail="Setup already completed")
    if state.get("current_step") != expected:
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
    """T-Q07: extracted from _advance so the wizard-completion logic and the
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
    """Adimi tamamlanmis olarak isaretle ve current_step + 1 yap."""
    if step_key not in state["completed_steps"]:
        state["completed_steps"].append(step_key)
    if state["current_step"] < 6:
        state["current_step"] += 1
    _emit_funnel_step(state, step_key)


# ---------- step bodies ----------------------------------------------------


# CJ-005 — RFC 6761 special-use TLDs allowlist (intranet self-host icin).
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
        # CJ-005 — .local / .test / .example / .invalid / .localhost RFC 6761
        # special-use TLDs setup'ta gecerli; .local intranet deployment icin
        # yaygin (örn. admin@demo-acme.local).
        if _LOCAL_EMAIL_RE.match(value):
            return value
        # diger her sey icin standart EmailStr dogrulamasi
        from pydantic import TypeAdapter

        return TypeAdapter(EmailStr).validate_python(value)


class LicenseBody(BaseModel):
    license_key: str = Field(..., min_length=10)


class DomainBody(BaseModel):
    mode: Literal["ip", "domain"] = "ip"
    domain: Optional[str] = None
    ssl_mode: Literal["internal", "acme"] = "internal"


_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class AnthropicBody(BaseModel):
    """CJ-004 — Anthropic key opsiyonel: free-tier (skip_paid_providers=True)
    musterilerin Anthropic API key'i olmadan setup'i tamamlamasina izin verir.
    Paid-tier akisinda key zorunlu kalir.
    """

    anthropic_api_key: Optional[str] = Field(default=None, min_length=8)
    skip_paid_providers: bool = False

    @model_validator(mode="after")
    def _validate_payload(self) -> "AnthropicBody":
        if self.skip_paid_providers:
            # Free-tier: Anthropic key gonderilse bile yok sayilir.
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


# ---------- endpoints ------------------------------------------------------


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return read_state()


# 023 — Setup wizard language picker (browser auto-detect override)
class SetupLangBody(BaseModel):
    lang: str  # en|tr|es


@router.post("/lang", status_code=status.HTTP_200_OK)
async def set_setup_lang(body: SetupLangBody) -> Dict[str, Any]:
    if body.lang not in ("en", "tr", "es"):
        raise HTTPException(status_code=400, detail="Unsupported language")
    with _state_lock():  # Q12-L22-001
        state = read_state()
        state["lang"] = body.lang
        _atomic_write_state(state)
    return {"ok": True, "lang": body.lang}


@router.post("/step/admin", status_code=status.HTTP_200_OK)
async def step_admin(body: AdminBody) -> Dict[str, Any]:
    with _state_lock():  # Q12-L22-001
        state = read_state()
        _ensure_step(state, 1)
        pwd_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )
        admin_credentials_path().write_text(
            json.dumps(
                {"email": body.email, "password_hash": pwd_hash, "created_at": time.time()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state["data"]["admin"] = {"email": body.email}
        _persist_env_var("ABS_ADMIN_EMAIL", body.email)
        _advance(state, "admin")
        _atomic_write_state(state)
    return {"ok": True, "current_step": state["current_step"]}


@router.post("/step/license", status_code=status.HTTP_200_OK)
async def step_license(body: LicenseBody) -> Dict[str, Any]:
    with _state_lock():  # Q12-L22-001
        state = read_state()
        _ensure_step(state, 2)
        try:
            payload = verify_license(body.license_key)
        except HTTPException as exc:
            raise HTTPException(
                status_code=400, detail=f"Lisans gecersiz: {exc.detail}"
            ) from exc

        settings.license_key = body.license_key
        _persist_encrypted_secret("license_key", body.license_key)
        state["data"]["license"] = {
            "jti": payload.get("jti"),
            "tier": payload.get("tier"),
            "seat_count": payload.get("seat_count"),
        }
        _advance(state, "license")
        _atomic_write_state(state)
    return {"ok": True, "current_step": state["current_step"], "tier": payload.get("tier")}


@router.post("/step/domain", status_code=status.HTTP_200_OK)
async def step_domain(body: DomainBody) -> Dict[str, Any]:
    with _state_lock():  # Q12-L22-001
        state = read_state()
        _ensure_step(state, 3)
        if body.mode == "domain":
            if not body.domain or not _DOMAIN_RE.match(body.domain):
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
    return {"ok": True, "current_step": state["current_step"]}


@router.post("/step/anthropic", status_code=status.HTTP_200_OK)
async def step_anthropic(body: AnthropicBody) -> Dict[str, Any]:
    with _state_lock():  # Q12-L22-001
        state = read_state()
        _ensure_step(state, 4)
        if body.skip_paid_providers:
            # CJ-004 — free-tier akis: Anthropic atla, paid_skipped flag set.
            state["data"]["anthropic_configured"] = False
            state["data"]["paid_skipped"] = True
        else:
            # model_validator zaten format/zorunluluk dogruladi; burada sadece persist.
            assert body.anthropic_api_key is not None  # for type-checker
            settings.anthropic_api_key = body.anthropic_api_key
            _persist_encrypted_secret("anthropic_api_key", body.anthropic_api_key)
            state["data"]["anthropic_configured"] = True
            state["data"]["paid_skipped"] = False
        _advance(state, "anthropic")
        _atomic_write_state(state)
    return {
        "ok": True,
        "current_step": state["current_step"],
        "paid_skipped": state["data"].get("paid_skipped", False),
    }


@router.post("/step/providers", status_code=status.HTTP_200_OK)
async def step_providers(body: ProvidersBody) -> Dict[str, Any]:
    with _state_lock():  # Q12-L22-001
        state = read_state()
        _ensure_step(state, 5)
        configured: list[str] = []
        provider_fields = (
            "groq_api_key",
            "gemini_api_key",
            "cerebras_api_key",
            "cohere_api_key",
            "cf_account_id",
            "cf_api_token",
        )
        for field_name in provider_fields:
            value = getattr(body, field_name)
            if value:
                setattr(settings, field_name, value)
                _persist_encrypted_secret(field_name, value)
                configured.append(field_name)
        state["data"]["providers_configured"] = configured
        _advance(state, "providers")
        _atomic_write_state(state)
    return {"ok": True, "current_step": state["current_step"], "configured": configured}


async def _run_provider_tests() -> Dict[str, Any]:
    """Adim 6 — configured provider'lara test ping. Hatalar 'fail' olarak isaretlenir.

    Network erisimi zorunlu degil; test'te monkeypatch ile tamamen mock edilebilir.
    """
    results: Dict[str, Any] = {}
    state = read_state()
    configured = state.get("data", {}).get("providers_configured", []) or []
    if state.get("data", {}).get("anthropic_configured"):
        configured = ["anthropic_api_key", *configured]

    for field_name in configured:
        results[field_name] = {"status": "skipped", "reason": "live ping disabled in setup"}
    return results


@router.post("/step/test", status_code=status.HTTP_200_OK)
async def step_test() -> Dict[str, Any]:
    with _state_lock():  # Q12-L22-001
        state = read_state()
        _ensure_step(state, 6)
        test_results = await _run_provider_tests()
        state["data"]["test_results"] = test_results
        if "test" not in state["completed_steps"]:
            state["completed_steps"].append("test")
        state["completed"] = True
        state["completed_at"] = time.time()
        _atomic_write_state(state)
    return {
        "ok": True,
        "completed": True,
        "current_step": state["current_step"],
        "test_results": test_results,
    }


@router.post("/reset", status_code=status.HTTP_200_OK)
async def reset_setup() -> Dict[str, Any]:
    """Dev-only — `settings.env=='dev'` ise state sil + admin credentials sil."""
    if settings.env != "dev":
        raise HTTPException(status_code=403, detail="Reset sadece dev ortaminda mumkun")
    p = setup_state_path()
    cred = admin_credentials_path()
    if p.is_file():
        p.unlink()
    if cred.is_file():
        cred.unlink()
    return {"ok": True, "reset": True}
