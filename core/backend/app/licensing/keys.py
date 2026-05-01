from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def load_private_key(path: str) -> bytes:
    """PEM formatında özel anahtarı okur. Dosya yoksa FileNotFoundError (TR)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Özel anahtar dosyası bulunamadı: {path}")
    return p.read_bytes()


def load_public_key(path: str) -> bytes:
    """PEM formatında genel anahtarı okur. Dosya yoksa FileNotFoundError (TR)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Genel anahtar dosyası bulunamadı: {path}")
    return p.read_bytes()


def generate_keypair(private_path: str, public_path: str) -> None:
    """2048-bit RSA çifti üretir, PEM olarak yazar. Özel anahtar izni 0o600."""
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
