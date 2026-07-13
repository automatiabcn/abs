# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""RSA keypair I/O and resolution of the image-baked vendor public key.

Distributed images bake the vendor's public key at
``/etc/abs/manifest_pubkey.pem`` and point ``ABS_PUBLIC_KEY_PATH`` at it;
verification reads it through ``settings.public_key_path``.

Minting must therefore use the private key that pairs with that public key —
never a keypair a container generated for itself, which would produce licenses
the verifier rejects as "signature invalid". A stale ``private.pem`` on a
persisted volume is exactly this trap, so minting is refused when the
configured private key does not derive the image-baked public key.

Environments with no image-baked public key (dev, test) are unaffected.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)

# Image-baked vendor public key. Dockerfile copies the vendor's PEM
# into this exact path and points ``ABS_PUBLIC_KEY_PATH`` at it.
IMAGE_BAKED_PUBLIC_KEY = Path("/etc/abs/manifest_pubkey.pem")


def load_private_key(path: str) -> bytes:
    """Read a PEM private key. Raises FileNotFoundError when it is missing."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Private key file not found: {path}")
    return p.read_bytes()


def load_public_key(path: str) -> bytes:
    """Read a PEM public key. Raises FileNotFoundError when it is missing."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Public key file not found: {path}")
    return p.read_bytes()


def generate_keypair(private_path: str, public_path: str) -> None:
    """Generate a 2048-bit RSA pair as PEM. The private key is written 0600."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv = Path(private_path)
    pub = Path(public_path)
    priv.parent.mkdir(parents=True, exist_ok=True)
    pub.parent.mkdir(parents=True, exist_ok=True)

    priv.write_bytes(private_bytes)
    pub.write_bytes(public_bytes)

    os.chmod(priv, 0o600)


def _public_pem_from_private(private_pem: bytes) -> bytes:
    """Derive the SubjectPublicKeyInfo PEM that matches a given private PEM."""
    priv = serialization.load_pem_private_key(private_pem, password=None)
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _normalised_pem(raw: bytes) -> bytes:
    """Strip whitespace + comments so byte comparison survives line-ending drift."""
    return b"".join(
        line.strip() for line in raw.splitlines() if line.strip()
    )


def assert_mint_keypair_pairs() -> None:
    """Refuse to mint when the configured private key does not match the
    image-baked vendor pubkey.

    Behaviour:
      * No image-baked pubkey on disk → no-op (dev/test).
      * ``ABS_LICENSE_MINT_INSECURE=1`` → no-op (vendor local-machine
        bootstraps before the shared key is provisioned).
      * Image-baked pubkey present + private key derives a different
        public key → ``RuntimeError`` with explicit guidance to set
        ``ABS_PRIVATE_KEY_PATH`` to the vendor's shared key.
    """

    if os.environ.get("ABS_LICENSE_MINT_INSECURE") == "1":
        return
    if not IMAGE_BAKED_PUBLIC_KEY.is_file():
        return

    from app.config import settings  # local import to avoid cycle at module load

    try:
        priv_pem = load_private_key(settings.private_key_path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "license_mint_no_private_key — image-baked pubkey is present at "
            f"{IMAGE_BAKED_PUBLIC_KEY} but no private key was found at "
            f"{settings.private_key_path!r}. Mint requires the vendor's "
            "shared private key. Set ABS_PRIVATE_KEY_PATH to the matching "
            "PEM and retry."
        ) from exc

    try:
        derived_pub = _public_pem_from_private(priv_pem)
    except Exception as exc:  # pragma: no cover — malformed PEM
        raise RuntimeError(
            f"license_mint_private_key_unreadable: {exc!s}"
        ) from exc

    baked_pub = IMAGE_BAKED_PUBLIC_KEY.read_bytes()
    if _normalised_pem(derived_pub) != _normalised_pem(baked_pub):
        logger.critical(
            "license_mint_pair_mismatch private=%s baked=%s",
            settings.private_key_path,
            IMAGE_BAKED_PUBLIC_KEY,
        )
        raise RuntimeError(
            "license_mint_pair_mismatch — the configured private key "
            f"({settings.private_key_path!r}) does not pair with the "
            f"image-baked public key ({IMAGE_BAKED_PUBLIC_KEY}). Mint must "
            "use the vendor's private signing key. Set "
            "ABS_PRIVATE_KEY_PATH to that PEM, or set "
            "ABS_LICENSE_MINT_INSECURE=1 only for a dev pair-bootstrap."
        )
