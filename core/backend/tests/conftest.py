"""Test fixture'ları — RSA keys + SQLite tmp DB + TestClient."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _session_env(tmp_path_factory):
    """Test sırasında izole dizin + RSA çifti + SQLite + dummy stripe secret."""
    tmpdir: Path = tmp_path_factory.mktemp("abs-test")

    private_path = tmpdir / "private.pem"
    public_path = tmpdir / "public.pem"
    db_path = tmpdir / "abs.db"
    env_file = tmpdir / ".env"
    env_file.write_text("", encoding="utf-8")

    # settings import'tan ÖNCE env var'ları set et (pydantic-settings load sırası)
    os.environ["ABS_PRIVATE_KEY_PATH"] = str(private_path)
    os.environ["ABS_PUBLIC_KEY_PATH"] = str(public_path)
    os.environ["ABS_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["ABS_STRIPE_WEBHOOK_SECRET"] = "whsec_test_dummy"
    os.environ["ABS_STRIPE_SECRET_KEY"] = "sk_test_dummy"
    os.environ["ABS_LICENSE_KEY"] = ""
    os.environ["ABS_TEST_MODE"] = "1"

    from app.config import settings  # noqa: WPS433
    from app.licensing.keys import generate_keypair

    # env → settings senkronu (import sırası nedeniyle güvence)
    settings.private_key_path = str(private_path)
    settings.public_key_path = str(public_path)
    settings.database_url = f"sqlite:///{db_path}"
    settings.stripe_webhook_secret = "whsec_test_dummy"
    settings.stripe_secret_key = "sk_test_dummy"
    settings.license_key = ""
    # model_config env_file yolunu test dizinine çek (persist testleri için)
    settings.model_config["env_file"] = str(env_file)

    generate_keypair(str(private_path), str(public_path))

    # DB init (tmp dir'de tabloları oluştur)
    from app.db.session import init_db

    # module-level engine cache'ini sıfırla
    import app.db.session as session_mod

    session_mod._engine = None
    init_db()

    yield


@pytest.fixture(scope="session", autouse=True)
def _session_data_dir(tmp_path_factory, _session_env):
    """012 — settings.data_dir test-session boyunca tmp'e sabitle. Default
    /app/data prod path'i write-only test ortaminda calismaz."""
    from app.config import settings

    tmp = tmp_path_factory.mktemp("abs-data")
    settings.data_dir = str(tmp)
    yield tmp


@pytest.fixture(autouse=True)
def _autocomplete_setup_state(_session_data_dir):
    """012 — first-run middleware mevcut testleri bozmasin diye varsayilan
    setup_state.json `completed:true` yaz. Setup wizard / first-run testleri
    `monkeypatch.setattr(settings, 'data_dir', tmp_path)` ile override
    ederek bu fixture'in yazdigini gormez."""
    import json
    import time
    from pathlib import Path

    from app.config import settings

    state_path = Path(settings.data_dir) / "setup_state.json"
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "completed": True,
                    "current_step": 6,
                    "completed_steps": [
                        "admin",
                        "license",
                        "domain",
                        "anthropic",
                        "providers",
                        "test",
                    ],
                    "started_at": time.time(),
                    "completed_at": time.time(),
                    "data": {},
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """028 — Reset slowapi in-memory storage between tests so rate limits
    don't leak across the suite (causing 429s in unrelated tests)."""
    try:
        from app.middleware.rate_limit import limiter

        limiter.reset()
    except Exception:
        pass
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
