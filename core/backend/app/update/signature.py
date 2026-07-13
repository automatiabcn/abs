# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""015 — Release manifest RS256 signature verification (fail-closed).

Tasarim:
  - Bizim taraf (release pipeline): private.pem ile imzala → manifest.json.sig
    `openssl dgst -sha256 -sign private.pem -out manifest.json.sig manifest.json`
    `base64 manifest.json.sig > manifest.json.sig.b64`
  - Musteri taraf: app/update/manifest_pubkey.pem ile verify
  - Manifest URL fetch + `.sig` URL fetch + verify
  - Fail-closed: imza yok / dogrulanamiyorsa state="unknown" + error="signature"

settings.update_signature_required default True (production guvenligi).
Set to False in development, where there is no manifest signing flow.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _pubkey_path() -> Path:
    return Path(__file__).parent / "manifest_pubkey.pem"


def verify_manifest(manifest_bytes: bytes, signature_b64: str) -> bool:
    """RS256 (PKCS1v15 + SHA256) verify. False = invalid (fail-closed)."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
    except ImportError:
        logger.warning("cryptography paketi yok — manifest signature skip (fail)")
        return False
    pubkey_path = _pubkey_path()
    if not pubkey_path.is_file():
        logger.warning("manifest pubkey yok: %s", pubkey_path)
        return False
    try:
        pubkey = serialization.load_pem_public_key(pubkey_path.read_bytes())
        if not isinstance(pubkey, rsa.RSAPublicKey):
            logger.warning("public key is not RSA")
            return False
        signature = base64.b64decode(signature_b64)
        pubkey.verify(
            signature,
            manifest_bytes,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as exc:
        logger.warning("manifest signature verify fail: %s", exc)
        return False


async def fetch_signature(manifest_url: str) -> Optional[str]:
    """`<manifest_url>.sig` cek (base64-encoded RS256 imza)."""
    sig_url = manifest_url + ".sig"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(sig_url)
        if r.status_code >= 400:
            return None
        return r.text.strip()
    except Exception as exc:
        logger.warning("signature fetch fail: %s", exc)
        return None
