"""GitHub App JWT + installation token + webhook."""

from __future__ import annotations

import hashlib
import hmac

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.integrations.github_app import (
    DEFAULT_MANIFEST,
    fetch_installation_token,
    generate_app_jwt,
    verify_webhook_signature,
)


def _generate_test_keypair():
    """Generate a small (1024-bit, fast) RSA keypair for tests."""
    from cryptography.hazmat.primitives import serialization

    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return pem, pub


@pytest.fixture(scope="module")
def _keys():
    return _generate_test_keypair()


def test_generate_app_jwt_signs_with_rs256(_keys):
    pem, pub = _keys
    token = generate_app_jwt(app_id="12345", private_key_pem=pem, ttl_seconds=300)
    payload = pyjwt.decode(token, pub, algorithms=["RS256"])
    assert payload["iss"] == "12345"
    assert payload["exp"] - payload["iat"] >= 300


def test_app_jwt_within_github_max_ttl(_keys):
    pem, _ = _keys
    token = generate_app_jwt(app_id="x", private_key_pem=pem, ttl_seconds=540)
    payload = pyjwt.decode(token, options={"verify_signature": False})
    # GitHub allows max 600s; we default to 540
    assert payload["exp"] - payload["iat"] <= 600


def test_fetch_installation_token_success(_keys, monkeypatch):
    pem, _ = _keys

    class _R:
        status_code = 201
        text = ""

        def json(self):
            return {
                "token": "ghs_install_test_token",
                "expires_at": "2026-04-27T15:00:00Z",
                "permissions": {"contents": "read"},
            }

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, *a, **kw):
            return _R()

        def close(self):
            pass

    monkeypatch.setattr(httpx, "Client", _Client)

    out = fetch_installation_token(
        app_id="123",
        installation_id="456",
        private_key_pem=pem,
        http_client=_Client(),
    )
    assert out["ok"] is True
    assert out["token"] == "ghs_install_test_token"
    assert "contents" in out["permissions"]


def test_fetch_installation_token_failure(_keys):
    pem, _ = _keys

    class _R:
        status_code = 404
        text = "Not Found"

    class _C:
        def post(self, *a, **kw):
            return _R()

        def close(self):
            pass

    out = fetch_installation_token(
        app_id="bad", installation_id="bad", private_key_pem=pem, http_client=_C()
    )
    assert out["ok"] is False
    assert out["status"] == 404


def test_verify_webhook_signature_pass_and_fail():
    secret = "github_webhook_secret_test"
    body = b'{"action":"created"}'
    expected_sig = (
        "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    )
    assert (
        verify_webhook_signature(
            secret=secret, body=body, signature_header=expected_sig
        )
        is True
    )
    assert (
        verify_webhook_signature(
            secret=secret, body=body, signature_header="sha256=" + "0" * 64
        )
        is False
    )
    assert (
        verify_webhook_signature(secret="", body=body, signature_header=expected_sig)
        is False
    )


def test_app_manifest_has_required_keys():
    for key in (
        "name",
        "url",
        "hook_attributes",
        "default_events",
        "default_permissions",
    ):
        assert key in DEFAULT_MANIFEST
    assert "push" in DEFAULT_MANIFEST["default_events"]
    assert DEFAULT_MANIFEST["default_permissions"]["contents"] in ("read", "write")


def test_webhook_endpoint_accepts_valid_signature(client, monkeypatch):
    secret = "wh_test_secret_long_enough"
    monkeypatch.setattr(settings, "github_app_webhook_secret", secret)
    body = b'{"action":"opened","number":1}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(
        "/v1/integrations/github/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["event"] == "pull_request"
    assert r.json()["action"] == "opened"
