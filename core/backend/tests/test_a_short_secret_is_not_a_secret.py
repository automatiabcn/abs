# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The boot guard checked that the operator changed the secret, not that they
changed it to anything worth having.

`validate_production_secrets` compares each secret against the placeholder that
ships in this repository, so an operator who leaves `ABS_SESSION_SECRET` unset
cannot boot in production. Good. But an operator who sets it to `hunter2` sailed
straight through — and every session cookie, every admin JWT, every unsubscribe
link is signed with it. A 6-byte HMAC key is a formality, not a signature.

PyJWT is blunt about this: keys below 32 bytes are under the minimum for SHA-256
(RFC 7518 §3.2) and it now warns on every encode. These tests hold the line at
the door instead: set-but-short is refused, with the name, the size, and the
command that produces a real one.
"""

from __future__ import annotations

import pytest

from app.config import (
    Settings,
    assert_production_safe,
    validate_secret_strength,
)

_REAL = "a" * 64  # what `openssl rand -hex 32` gives you


def _prod(**overrides: object) -> Settings:
    """A production deployment with every placeholder already replaced, so the
    only thing under test is secret *strength*."""
    base: dict[str, object] = {
        "env": "prod",
        "unsubscribe_jwt_secret": _REAL,
        "admin_token": _REAL,
        "audit_ip_salt": _REAL,
        "delete_confirm_jwt_secret": _REAL,
        "beta_admin_token": _REAL,
        "admin_jwt_secret": _REAL,
        "session_secret": _REAL,
        "admin_password_bootstrap": _REAL,
        "vault_audit_hmac_secret": _REAL,
        "neo4j_password": _REAL,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_a_properly_generated_secret_boots() -> None:
    assert validate_secret_strength(_prod()) == []
    assert_production_safe(_prod())  # does not raise


def test_a_short_session_secret_refuses_the_boot() -> None:
    """The session secret signs the cookie that says who you are. Short is not
    a style preference."""
    with pytest.raises(RuntimeError) as exc:
        assert_production_safe(_prod(session_secret="hunter2"))

    message = str(exc.value)
    assert "session_secret" in message
    assert "7 bytes" in message, "the operator should not have to count"
    assert "openssl rand -hex 32" in message, "tell them how to fix it"


@pytest.mark.parametrize(
    "name",
    [
        "admin_jwt_secret",
        "admin_token",
        "beta_admin_token",
        "unsubscribe_jwt_secret",
        "delete_confirm_jwt_secret",
        "vault_audit_hmac_secret",
        "audit_ip_salt",
    ],
)
def test_every_signing_secret_is_held_to_the_same_floor(name: str) -> None:
    """One weak key is enough — whichever it is."""
    weak = validate_secret_strength(_prod(**{name: "short"}))
    assert any(w.startswith(name) for w in weak), f"{name} was not checked"


def test_thirty_one_bytes_is_refused_and_thirty_two_is_not() -> None:
    """Where the line actually falls, so nobody has to guess it from prose."""
    assert validate_secret_strength(_prod(session_secret="x" * 31)) != []
    assert validate_secret_strength(_prod(session_secret="x" * 32)) == []


def test_an_empty_required_secret_refuses_the_boot() -> None:
    """`.env.example` ships these blank. An operator who copies it and fills in
    only the lines they recognise leaves `ABS_SESSION_SECRET=` empty — and empty
    is not the placeholder, so the old guard blessed the deployment. The server
    booted, and PyJWT raised `InvalidKeyError: HMAC key must not be empty` on the
    first sign-in: a server nobody can log into, pronounced safe."""
    with pytest.raises(RuntimeError) as exc:
        assert_production_safe(_prod(session_secret=""))

    assert "session_secret" in str(exc.value)
    assert "empty" in str(exc.value)


def test_an_optional_secret_that_is_unset_is_not_a_weak_secret() -> None:
    """`mcp_token_secret` and `magic_link_hmac_secret` default to empty: the
    feature they key is simply off. Reporting them would train the operator to
    ignore this error."""
    weak = validate_secret_strength(_prod(mcp_token_secret="", magic_link_hmac_secret=""))
    assert weak == []


def test_a_development_box_is_left_alone() -> None:
    """The floor applies where the server is reachable. A laptop keeps its
    throwaway secrets, or nobody can run the thing."""
    dev = Settings(env="dev", session_secret="short")
    assert_production_safe(dev)  # does not raise
