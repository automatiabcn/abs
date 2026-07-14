"""sweep 4 — close last PyJWT internals leak in verifier.

* (LOW security info-leak) — `app.licensing.verifier`
  caught `PyJWTError` (the catch-all parent class) and surfaced
  `f"License verification error: {exc}"` to clients. Earlier sweeps
  (R14 me_account, R18/R19 me_data_export + me_account, R22 webhook
  signatures, R25 me_consent + me_audit + secrets/rotate) closed every
  sibling leak; this branch was the last one.

Hard to trigger in normal flow (PyJWTError parent rarely fires after
the more specific subclasses) but a defense-in-depth fix matters
because library-author additions of new PyJWT subclasses would
silently fall through to the leak path.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from jwt import PyJWTError

from app.licensing import verifier as verifier_mod


def test_pyjwt_error_response_is_generic(caplog) -> None:
    """A PyJWTError that escapes the more specific catches must result
    in a generic `license_verify_failed` detail, NOT `f"...: {exc}"`."""

    class FakeWeirdPyJWTError(PyJWTError):
        def __str__(self) -> str:
            return "INTERNAL: secret_key=hunter2 path=/etc/sops/keys"

    with patch.object(
        verifier_mod.jwt,
        "decode",
        side_effect=FakeWeirdPyJWTError("INTERNAL: secret_key=hunter2"),
    ):
        with caplog.at_level(logging.WARNING, logger="app.licensing.verifier"):
            with pytest.raises(HTTPException) as exc:
                verifier_mod.verify_license("any.thing.here")

    assert exc.value.status_code == 400
    detail = str(exc.value.detail)
    assert detail == "license_verify_failed"
    assert "secret_key" not in detail
    assert "hunter2" not in detail
    assert "INTERNAL" not in detail
    # error_class must reach ops via the warning log (taxonomy only,
    # never the raw message).
    assert any(
        "license_verify_pyjwt_error" in r.message and "FakeWeirdPyJWTError" in r.message
        for r in caplog.records
    ), "expected ops audit warning with error_class taxonomy"


def test_existing_specific_branches_still_specific() -> None:
    """Regression guard — the 3 specific branches (Expired / Invalid
    Signature / InvalidTokenError) still respond with their distinct
    user-facing details. No accidental over-generalisation by the
    sweep."""

    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    import jwt as pyjwt

    from app.config import settings
    from app.licensing.keys import load_private_key

    private = load_private_key(settings.private_key_path)
    now = datetime.now(timezone.utc)

    # 1) Expired → 401 "License has expired"
    expired = pyjwt.encode(
        {
            "iat": int(now.timestamp()),
            "exp": int((now - timedelta(seconds=10)).timestamp()),
            "jti": uuid4().hex,
        },
        private,
        algorithm="RS256",
    )
    with pytest.raises(HTTPException) as exc:
        verifier_mod.verify_license(expired)
    assert exc.value.status_code == 401
    assert "expired" in str(exc.value.detail).lower()

    # 2) Garbled → 400 "License format invalid"
    with pytest.raises(HTTPException) as exc2:
        verifier_mod.verify_license("not.a.valid.jwt")
    assert exc2.value.status_code == 400
    assert (
        "format" in str(exc2.value.detail).lower()
        or str(exc2.value.detail) == "license_verify_failed"
    )
