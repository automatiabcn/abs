"""Test fixtures — RSA keys + a SQLite tmp DB + the TestClient."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Filled in by `_session_env`: the live SQLite file every test talks to, and a
# pristine copy of it taken right after the tables were created.
_DB_PATHS: dict[str, Path] = {}


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

    # Keep a pristine copy of the freshly-migrated database. `_isolate_db` below
    # restores it before every test, so no test inherits another's rows.
    import shutil

    pristine = tmpdir / "pristine.db"
    shutil.copyfile(db_path, pristine)
    _DB_PATHS["live"] = db_path
    _DB_PATHS["pristine"] = pristine

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
    """Hand every test an empty data directory with a `completed: true`
    setup_state.json, so the first-run middleware does not hijack it.

    Emptying the directory matters as much as writing the state file. The admin's
    credentials live on disk, in `admin_credentials.json`, not in the database —
    and the setup-wizard tests write that file. It used to survive into every test
    that ran after them, which meant `admin@local` / `CHANGEME` stopped being the
    password and a hundred unrelated tests got a 401 from a wizard they never ran.
    Whether that happened depended on the collection order.

    The setup-wizard and first-run tests point `settings.data_dir` somewhere else
    with monkeypatch, so none of this touches them."""
    import json
    import shutil
    import time
    from pathlib import Path

    from app.config import settings

    data_dir = Path(settings.data_dir)
    state_path = data_dir / "setup_state.json"
    try:
        if data_dir.exists():
            shutil.rmtree(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
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
def _restore_settings():
    """Hand back the settings object exactly as the test found it.

    `settings` is one object for the whole process. Most tests change it through
    monkeypatch and get their change undone for free; the ones that assign to it
    directly do not, and what they leave behind is invisible until some later test
    asks a question whose answer depends on it. That is how a test asserting "groq
    is not configured" ended up reading a key another test had set an hour of
    collection order earlier.
    """
    from app.config import settings

    before = dict(settings.__dict__)
    yield
    settings.__dict__.clear()
    settings.__dict__.update(before)


@pytest.fixture(autouse=True)
def _reset_health_monitor():
    """The health monitor is another process-wide singleton, and the probe results
    it collects were outliving the test that provoked them — so a test asserting
    that a fresh monitor reports every provider as `unknown` read a neighbour's
    results instead."""
    try:
        from app.health.monitor import monitor

        monitor._results.clear()
    except Exception:
        pass
    try:
        # The SSE judge feed caches its aggregate for 60s in a module-level dict.
        # Inside a test run that is longer than the whole suite: one test writes a
        # score into it and every later test that reads the feed gets that score
        # back instead of the empty one it set up for.
        from app.api.stream import _JUDGE_CACHE

        _JUDGE_CACHE["data"] = None
        _JUDGE_CACHE["ts"] = 0.0
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


@pytest.fixture(autouse=True)
def _isolate_db():
    """Give every test the database as it was before any test touched it.

    One SQLite file was shared by the whole session, so every row a test wrote
    was still there for the next one. That is how the suite ended up green in
    exactly one collection order and red in others:

      * `FailedLoginAttempt` — dozens of tests submit a bad password on purpose,
        because that is the thing they are testing. Each one pushes `admin@local`
        closer to a lockout, and whichever test crosses the threshold hands every
        later admin login a 429 before the password is even checked.
      * `Tenant` — the raw-Cypher guard refuses when the install serves more than
        one tenant. Tests that create tenants leave them behind, so a graph test
        that would pass alone gets a 403 from a neighbour's rows.
      * The admin's password, provider keys, secrets — all of it carried over.

    Restoring a pristine copy of the file is cheap (SQLite is one file, and the
    copy is milliseconds) and it closes the whole class rather than one symptom
    at a time. The engine is disposed first so its pooled connections do not keep
    writing to the file we are about to overwrite.
    """
    import shutil

    live = _DB_PATHS.get("live")
    pristine = _DB_PATHS.get("pristine")
    if live and pristine and pristine.exists():
        try:
            import app.db.session as session_mod

            if session_mod._engine is not None:
                session_mod._engine.dispose()
            shutil.copyfile(pristine, live)
        except Exception:
            pass
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
