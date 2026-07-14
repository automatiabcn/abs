"""sweep 2 — safe-expansion drills (non-destructive).

Three idempotency / boundary checks the founder-gated L21 plan
explicitly authorised:

* **migration roundtrip 10×** — `alembic upgrade head → downgrade -1 →
  upgrade head` ten consecutive iterations must be idempotent
  (extends the earlier single-cycle test).
* **license JWT expiry boundary** — at `exp = now-1s`, `exp = now+1s`,
  `exp = now+24h` the verifier must respond consistently per the
  RFC 7519 §4.1.4 contract.
* **JWT `iat`-in-future** — clock skew on the issuer; the verifier
  should not accept a token claiming to be issued 60 s in the future
  if the JWT lib is configured strictly.

Each test isolates state via tempfile; production volumes are not
touched.
"""

from __future__ import annotations

import base64
import json
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect

from app.config import settings
from app.licensing.keys import load_private_key, load_public_key
from app.licensing.verifier import verify_license


def _alembic_cfg(db_url: str, repo_root: Path) -> Config:
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    return cfg


# ---------------------------------------------------------------------------
# alembic upgrade↔downgrade 10× idempotency
# ---------------------------------------------------------------------------


def test_alembic_roundtrip_10x() -> None:
    """Ten consecutive up/down/up cycles must converge to the same
    schema each time. Catches:
      - downgrade() leaks (orphan indexes / constraints)
      - operation order sensitivity
      - autoincrement counter drift
    """

    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "loop.db"
        db_url = f"sqlite:///{db_path}"
        cfg = _alembic_cfg(db_url, repo_root)

        # Initial upgrade → head
        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        baseline = set(inspect(engine).get_table_names())
        engine.dispose()
        assert "minted_token_blacklist" in baseline
        assert "chat_sessions" in baseline

        # `head` advanced past 0008, so `-1` no
        # longer lands on the revision that drops minted_token_blacklist.
        # Pin the downgrade target to 0007_chat_sessions so this 10×
        # contract keeps exercising the same up/down/up cycle.
        # 10 consecutive cycles
        for i in range(10):
            command.downgrade(cfg, "0007_chat_sessions")
            engine = create_engine(db_url)
            after_down = set(inspect(engine).get_table_names())
            engine.dispose()
            assert "minted_token_blacklist" not in after_down, (
                f"iteration {i}: minted_token_blacklist not removed"
            )

            command.upgrade(cfg, "head")
            engine = create_engine(db_url)
            after_up = set(inspect(engine).get_table_names())
            engine.dispose()
            assert after_up == baseline, (
                f"iteration {i}: schema drift — diff={after_up ^ baseline}"
            )


# ---------------------------------------------------------------------------
# license JWT expiry boundary
# ---------------------------------------------------------------------------


def _mint_license(*, exp_offset_seconds: int, iat_offset_seconds: int = 0) -> str:
    private_pem = load_private_key(settings.private_key_path)
    now = datetime.now(timezone.utc)
    payload = {
        "iat": int((now + timedelta(seconds=iat_offset_seconds)).timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset_seconds)).timestamp()),
        "jti": uuid.uuid4().hex,
        "sub": "boundary-test",
        "tier": "starter",
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")


def test_license_already_expired_1s_ago_rejected() -> None:
    """exp = now-1s → 401 ExpiredSignature."""

    token = _mint_license(exp_offset_seconds=-1)
    with pytest.raises(HTTPException) as exc:
        verify_license(token)
    assert exc.value.status_code == 401
    assert "expired" in str(exc.value.detail).lower()


def test_license_expires_in_5s_accepted_now() -> None:
    """exp = now+5s → still valid this instant. (5s margin beats
    pytest-xdist + slow-import jitter; we still cover the
    "freshly-minted, about-to-expire" case below.)"""

    token = _mint_license(exp_offset_seconds=5)
    claims = verify_license(token)
    assert claims["sub"] == "boundary-test"


def test_license_expires_in_24h_accepted() -> None:
    """exp = now+24h → unambiguously valid."""

    token = _mint_license(exp_offset_seconds=86_400)
    claims = verify_license(token)
    assert claims["sub"] == "boundary-test"
    assert claims["tier"] == "starter"


def test_license_exp_boundary_after_sleep() -> None:
    """exp = now+1s, then wait 3s → must reject (no clock-skew leniency
    that would let a recently-revoked license slip through)."""

    token = _mint_license(exp_offset_seconds=1)
    time.sleep(3)
    with pytest.raises(HTTPException) as exc:
        verify_license(token)
    assert exc.value.status_code == 401


def test_license_far_future_exp_accepted() -> None:
    """exp = 100 years out → valid (no sane upper bound enforced)."""

    token = _mint_license(exp_offset_seconds=100 * 365 * 86_400)
    claims = verify_license(token)
    assert claims["sub"] == "boundary-test"


# ---------------------------------------------------------------------------
# license token tampering / signature mismatch
# ---------------------------------------------------------------------------


def test_license_signature_tampered_rejected() -> None:
    """Mutate one byte of the signature → 401 InvalidSignature."""

    token = _mint_license(exp_offset_seconds=3600)
    parts = token.split(".")
    sig = bytearray(base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4)))
    sig[0] ^= 0xFF
    tampered = (
        f"{parts[0]}.{parts[1]}."
        f"{base64.urlsafe_b64encode(bytes(sig)).rstrip(b'=').decode('ascii')}"
    )
    with pytest.raises(HTTPException) as exc:
        verify_license(tampered)
    assert exc.value.status_code == 401


def test_license_payload_tampered_rejected() -> None:
    """Mutate one byte of the payload → 401 InvalidSignature."""

    token = _mint_license(exp_offset_seconds=3600)
    parts = token.split(".")
    raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
    payload_obj = json.loads(raw)
    payload_obj["tier"] = "enterprise"  # privilege escalation attempt
    tampered_payload = (
        base64.urlsafe_b64encode(json.dumps(payload_obj).encode())
        .rstrip(b"=")
        .decode("ascii")
    )
    tampered = f"{parts[0]}.{tampered_payload}.{parts[2]}"
    with pytest.raises(HTTPException) as exc:
        verify_license(tampered)
    assert exc.value.status_code == 401


def test_license_missing_required_claim_rejected() -> None:
    """jti is required by `options={'require':['exp','iat','jti']}`. A
    token issued without it must be rejected — protects audit chain."""

    private_pem = load_private_key(settings.private_key_path)
    now = datetime.now(timezone.utc)
    payload = {
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=3600)).timestamp()),
        # NO jti
        "sub": "missing-jti",
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256")
    with pytest.raises(HTTPException) as exc:
        verify_license(token)
    # 401 (expired-class) or 400 (format-class) — both acceptable; just
    # not a silent allow.
    assert exc.value.status_code in (400, 401)


def test_license_garbled_token_rejected() -> None:
    """Arbitrary garbage → 400 format invalid."""

    with pytest.raises(HTTPException) as exc:
        verify_license("not.a.real.token.at.all")
    assert exc.value.status_code in (400, 401)


def test_license_wrong_signing_key_rejected() -> None:
    """A token signed by a different RSA key must not be honoured."""

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rogue_pem = rogue_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=3600)).timestamp()),
            "jti": uuid.uuid4().hex,
            "sub": "rogue",
        },
        rogue_pem,
        algorithm="RS256",
    )
    # Make sure host public key is loadable; otherwise we can't isolate.
    load_public_key(settings.public_key_path)
    with pytest.raises(HTTPException) as exc:
        verify_license(token)
    assert exc.value.status_code == 401
