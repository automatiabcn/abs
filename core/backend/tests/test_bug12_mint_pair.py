# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""BUG-12 — generate_license must refuse to mint when the configured
private key does not pair with the image-baked founder pubkey.

The image-baked path is detected via the module-level
``IMAGE_BAKED_PUBLIC_KEY`` constant; we monkeypatch it onto a tmp file
so the real ``/etc/abs/manifest_pubkey.pem`` (absent on dev hosts) is
not required for the test to be meaningful.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.licensing import generate_license
from app.licensing import keys as keys_mod
from app.licensing.keys import generate_keypair


def _write_pair(tmp: Path) -> tuple[str, str]:
    priv = tmp / "founder_private.pem"
    pub = tmp / "founder_public.pem"
    generate_keypair(str(priv), str(pub))
    return str(priv), str(pub)


def test_mint_succeeds_when_pair_matches_baked_pubkey(tmp_path, monkeypatch):
    priv_path, pub_path = _write_pair(tmp_path)
    monkeypatch.setattr(keys_mod, "IMAGE_BAKED_PUBLIC_KEY", Path(pub_path))

    from app.config import settings

    monkeypatch.setattr(settings, "private_key_path", priv_path)

    token = generate_license(
        "pair-ok@example.com", tier="self-host", seat_count=1, valid_days=30
    )
    assert token.count(".") == 2  # JWT shape


def test_mint_refuses_pair_mismatch(tmp_path, monkeypatch):
    # Founder shipped pubkey #1, container has rogue private #2.
    _, pub_path = _write_pair(tmp_path)
    rogue_priv = tmp_path / "rogue_private.pem"
    rogue_pub = tmp_path / "rogue_public.pem"
    generate_keypair(str(rogue_priv), str(rogue_pub))

    monkeypatch.setattr(keys_mod, "IMAGE_BAKED_PUBLIC_KEY", Path(pub_path))

    from app.config import settings

    monkeypatch.setattr(settings, "private_key_path", str(rogue_priv))

    with pytest.raises(RuntimeError, match="license_mint_pair_mismatch"):
        generate_license("rogue@x.local", tier="self-host", valid_days=1)


def test_mint_insecure_env_bypasses_pair_check(tmp_path, monkeypatch):
    """ABS_LICENSE_MINT_INSECURE=1 is the dev escape hatch."""
    _, pub_path = _write_pair(tmp_path)
    rogue_priv = tmp_path / "rogue_private.pem"
    rogue_pub = tmp_path / "rogue_public.pem"
    generate_keypair(str(rogue_priv), str(rogue_pub))

    monkeypatch.setattr(keys_mod, "IMAGE_BAKED_PUBLIC_KEY", Path(pub_path))
    monkeypatch.setenv("ABS_LICENSE_MINT_INSECURE", "1")

    from app.config import settings

    monkeypatch.setattr(settings, "private_key_path", str(rogue_priv))

    token = generate_license(
        "dev@x.local", tier="self-host", seat_count=1, valid_days=1
    )
    assert token.count(".") == 2


def test_mint_works_when_no_baked_pubkey(monkeypatch):
    """Dev/test environments without /etc/abs/manifest_pubkey.pem keep
    behaving as before — the conftest tmp keypair just signs."""
    bogus = Path("/nonexistent/path/manifest_pubkey.pem")
    monkeypatch.setattr(keys_mod, "IMAGE_BAKED_PUBLIC_KEY", bogus)

    token = generate_license(
        "dev-noenv@x.local", tier="self-host", seat_count=1, valid_days=1
    )
    assert token.count(".") == 2


def test_mint_refuses_when_baked_pubkey_present_but_private_missing(
    tmp_path, monkeypatch
):
    _, pub_path = _write_pair(tmp_path)
    monkeypatch.setattr(keys_mod, "IMAGE_BAKED_PUBLIC_KEY", Path(pub_path))

    from app.config import settings

    monkeypatch.setattr(
        settings, "private_key_path", str(tmp_path / "missing.pem")
    )

    with pytest.raises(RuntimeError, match="license_mint_no_private_key"):
        generate_license("missing@x.local", tier="self-host", valid_days=1)
