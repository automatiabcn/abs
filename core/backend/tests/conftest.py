"""Test fixtures — RSA keys + a SQLite tmp DB + the TestClient."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _session_env(tmp_path_factory):
    """An isolated directory, an RSA pair, SQLite, and a dummy Stripe secret."""
    tmpdir: Path = tmp_path_factory.mktemp("abs-test")

    private_path = tmpdir / "private.pem"
    public_path = tmpdir / "public.pem"
    db_path = tmpdir / "abs.db"
    env_file = tmpdir / ".env"
    env_file.write_text("", encoding="utf-8")

    # Set the env vars BEFORE settings is imported — pydantic-settings reads them at import.
    os.environ["ABS_PRIVATE_KEY_PATH"] = str(private_path)
    os.environ["ABS_PUBLIC_KEY_PATH"] = str(public_path)
    os.environ["ABS_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["ABS_STRIPE_WEBHOOK_SECRET"] = "whsec_test_dummy"
    os.environ["ABS_STRIPE_SECRET_KEY"] = "sk_test_dummy"
    os.environ["ABS_LICENSE_KEY"] = ""
    os.environ["ABS_TEST_MODE"] = "1"

    from app.config import settings  # noqa: WPS433
    from app.licensing.keys import generate_keypair

    # Sync env → settings, in case the import order got there first.
    settings.private_key_path = str(private_path)
    settings.public_key_path = str(public_path)
    settings.database_url = f"sqlite:///{db_path}"
    settings.stripe_webhook_secret = "whsec_test_dummy"
    settings.stripe_secret_key = "sk_test_dummy"
    settings.license_key = ""
    # Point model_config's env_file at the test directory (the persistence tests need it).
    settings.model_config["env_file"] = str(env_file)

    generate_keypair(str(private_path), str(public_path))

    # Create the tables in the tmp dir.
    from app.db.session import init_db

    # Reset the module-level engine cache.
    import app.db.session as session_mod

    session_mod._engine = None
    init_db()

    yield


@pytest.fixture(scope="session", autouse=True)
def _session_data_dir(tmp_path_factory, _session_env):
    """Pin settings.data_dir to a tmp dir for the whole session. The default
    /app/data is a production path and is not writable under test."""
    from app.config import settings

    tmp = tmp_path_factory.mktemp("abs-data")
    settings.data_dir = str(tmp)
    yield tmp


@pytest.fixture(autouse=True)
def _autocomplete_setup_state(_session_data_dir):
    """Write a `completed: true` setup_state.json so the first-run middleware
    does not hijack every other test. The setup-wizard and first-run tests
    override `settings.data_dir` with monkeypatch, so they never see this."""
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
    """Reset slowapi's in-memory storage between tests so rate limits don't leak
    across the suite and 429 an unrelated test."""
    try:
        from app.middleware.rate_limit import limiter

        limiter.reset()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """The breaker is a process-wide singleton and its failure counts were
    surviving from one test into the next.

    Five provider failures inside a minute open it, and this suite has far more
    than five tests that fail a provider on purpose. Once it is open, `allow()`
    refuses that provider — so a later test that mocks a *successful* call never
    sees its mock called at all: the cascade skips the provider and reports that
    everything failed. The test then fails for a reason unrelated to what it
    asserts, and *which* tests fail depends on the order the files happen to be
    collected in, which is why nobody noticed.

    Same class of leak the rate limiter above already guards against.
    """
    try:
        from app.cascade.breaker import default_breaker

        default_breaker._states.clear()
    except Exception:
        pass
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
