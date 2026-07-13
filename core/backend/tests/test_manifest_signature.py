"""015 — Manifest RS256 signature verify testleri (tmp keypair)."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import httpx
import pytest
import respx


@pytest.fixture(scope="module")
def tmp_keypair(tmp_path_factory):
    """Test'e ozel RSA-4096 keypair (subprocess openssl)."""
    d = tmp_path_factory.mktemp("manifest-keys")
    priv = d / "priv.pem"
    pub = d / "pub.pem"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(priv),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "rsa", "-pubout", "-in", str(priv), "-out", str(pub)],
        check=True,
        capture_output=True,
    )
    return {"private": priv, "public": pub, "dir": d}


def _sign_bytes(private_pem: Path, data: bytes) -> str:
    """openssl ile imza al, base64 dondur."""
    sig_path = private_pem.parent / "sig.bin"
    sig_path.write_bytes(b"")
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_pem),
            "-out",
            str(sig_path),
        ],
        input=data,
        capture_output=True,
        check=True,
    )
    return base64.b64encode(sig_path.read_bytes()).decode("ascii")


def test_verify_returns_false_when_no_pubkey(monkeypatch, tmp_path):
    from app.update import signature as sig_mod

    monkeypatch.setattr(sig_mod, "_pubkey_path", lambda: tmp_path / "missing.pem")
    assert sig_mod.verify_manifest(b"data", "anysig") is False


def test_verify_with_valid_signature(monkeypatch, tmp_keypair):
    from app.update import signature as sig_mod

    monkeypatch.setattr(sig_mod, "_pubkey_path", lambda: tmp_keypair["public"])
    payload = b'{"current_version":"0.2.0","critical":false}'
    sig = _sign_bytes(tmp_keypair["private"], payload)
    assert sig_mod.verify_manifest(payload, sig) is True


def test_verify_with_tampered_manifest(monkeypatch, tmp_keypair):
    from app.update import signature as sig_mod

    monkeypatch.setattr(sig_mod, "_pubkey_path", lambda: tmp_keypair["public"])
    original = b'{"current_version":"0.2.0"}'
    sig = _sign_bytes(tmp_keypair["private"], original)
    tampered = b'{"current_version":"99.0.0"}'  # malicious change
    assert sig_mod.verify_manifest(tampered, sig) is False


@pytest.mark.asyncio
@respx.mock
async def test_fetch_manifest_rejects_unsigned_when_required(monkeypatch, tmp_path):
    """Signature required + .sig 404 → state="unknown", error contains "signature"."""
    from app.config import settings
    from app.update.manifest import fetch_manifest, update_state

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(
        settings, "update_manifest_url", "https://abs.local/manifest.json"
    )
    monkeypatch.setattr(settings, "update_signature_required", True)
    respx.get("https://abs.local/manifest.json").mock(
        return_value=httpx.Response(200, json={"current_version": "0.2.0"})
    )
    respx.get("https://abs.local/manifest.json.sig").mock(
        return_value=httpx.Response(404)
    )
    manifest = await fetch_manifest(force=True)
    assert "error" in manifest
    assert "signature" in manifest["error"].lower()
    state = update_state(manifest, "0.1.0")
    assert state["state"] == "unknown"
    assert "signature" in state["error"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_manifest_skips_verify_when_disabled(monkeypatch, tmp_path):
    """update_signature_required=False → imza atla (dev mode)."""
    from app.config import settings
    from app.update.manifest import fetch_manifest

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(
        settings, "update_manifest_url", "https://abs.local/manifest.json"
    )
    monkeypatch.setattr(settings, "update_signature_required", False)
    respx.get("https://abs.local/manifest.json").mock(
        return_value=httpx.Response(200, json={"current_version": "0.2.0"})
    )
    manifest = await fetch_manifest(force=True)
    assert manifest.get("current_version") == "0.2.0"
    assert "error" not in manifest
