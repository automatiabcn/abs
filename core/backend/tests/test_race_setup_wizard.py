"""race condition deep: setup wizard TOCTOU.

Closes (HIGH installation-phase data corruption):
`/v1/setup/step/admin` (and the other step endpoints) follow the
classic TOCTOU pattern:

  state = read_state()                 # ← non-locking JSON read
  _ensure_step(state, expected_step)   # ← check
  # ... do work, mutate state ...      # ← race window (microseconds)
  _atomic_write_state(state)           # ← non-locking JSON write

Two concurrent admins POSTing to /step/admin both see the same
`current_step=1`, both pass `_ensure_step`, both write
`admin_credentials.json` (last writer wins on disk), both call
`_advance` and `_atomic_write_state` (last writer wins on disk).

Result pre-fix: BOTH return HTTP 200, with `admin_credentials.json`
silently containing whichever email was written last. The losing
admin has NO indication their credentials were overwritten.

Real-world scenario: SME pilot install where co-founders open the
setup URL on two tabs, click through the wizard at the same time.
Co-founder A's credentials are silently dropped; co-founder B can
log in but A is locked out — no error message either side.

Fix: wrap read-modify-write in an exclusive file-lock
(`fcntl.LOCK_EX` on a companion `.lock` file). One request enters
the critical section at a time. The losing call observes the
already-advanced state on its read and returns HTTP 409 from
`_ensure_step`, surfacing the conflict.

This is the canonical solution: works for multi-worker uvicorn
(several processes), no in-process state, simple and audited.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


# ----------------------------------------------------------------------
# Fixture: wipe setup_state.json so the wizard restarts at step 1.
# (Mirrors test_fresh_deploy_drill setup pattern.)
# ----------------------------------------------------------------------


@pytest.fixture
def fresh_setup_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    settings.model_config["env_file"] = str(env_file)
    sp = tmp_path / "setup_state.json"
    sp.write_text(
        json.dumps(
            {
                "completed": False,
                "current_step": 1,
                "completed_steps": [],
                "started_at": 0,
                "data": {},
            }
        ),
        encoding="utf-8",
    )
    yield tmp_path


# ----------------------------------------------------------------------
# Helper: drive step/admin concurrently via ASGI transport.
# ----------------------------------------------------------------------


async def _post_admin(client: AsyncClient, email: str, password: str) -> int:
    r = await client.post(
        "/v1/setup/step/admin",
        json={"email": email, "password": password},
    )
    return r.status_code


# ----------------------------------------------------------------------
# 1) Concurrent POST /step/admin: exactly ONE wins, other 409.
# ----------------------------------------------------------------------


class TestSetupWizardRace:
    @pytest.mark.asyncio
    async def test_concurrent_step_admin_one_winner(
        self, fresh_setup_state: Path
    ) -> None:
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            results = await asyncio.gather(
                _post_admin(client, "alice@l22.test", "AlicePass2026!"),
                _post_admin(client, "bob@l22.test", "BobPass2026!"),
                return_exceptions=False,
            )

        # fix contract: exactly one 200 + one 409. Pre-fix
        # both would be 200 with silent overwrite.
        assert sorted(results) == [200, 409], (
            f"REGRESSION: expected one 200 + one 409, got {results}. "
            "Setup wizard step endpoints lost TOCTOU protection."
        )

        # Confirm only ONE email survived (last-write-wins risk eliminated).
        creds_path = fresh_setup_state / "admin_credentials.json"
        assert creds_path.is_file()
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
        assert creds["email"] in {"alice@l22.test", "bob@l22.test"}

        # State must show current_step advanced exactly ONCE.
        state = json.loads(
            (fresh_setup_state / "setup_state.json").read_text(encoding="utf-8")
        )
        assert state["current_step"] == 2, (
            f"REGRESSION: state did not advance to step 2 "
            f"after one successful step/admin (got current_step={state['current_step']})"
        )
        # 'admin' must appear exactly once in completed_steps.
        admin_count = sum(1 for k in state["completed_steps"] if k == "admin")
        assert admin_count == 1, (
            f"REGRESSION: 'admin' completed {admin_count} times (double-advance leak)"
        )

    @pytest.mark.asyncio
    async def test_serial_step_admin_second_returns_409(
        self, fresh_setup_state: Path
    ) -> None:
        """Sanity: when calls are serialized, second one MUST also be 409.

        Pin the pre-existing _ensure_step contract so it doesn't regress
        while we're around the same code path.
        """
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r1 = await client.post(
                "/v1/setup/step/admin",
                json={"email": "alice@l22.test", "password": "AlicePass2026!"},
            )
            assert r1.status_code == 200
            r2 = await client.post(
                "/v1/setup/step/admin",
                json={"email": "bob@l22.test", "password": "BobPass2026!"},
            )
            assert r2.status_code == 409


# ----------------------------------------------------------------------
# 2) Lock helper unit contract — exclusive critical section.
# ----------------------------------------------------------------------


class TestStateLockHelper:
    def test_state_lock_provides_exclusive_access(
        self, fresh_setup_state: Path
    ) -> None:
        """Direct test of the _state_lock() context manager with TWO
        OS threads colliding on a barrier. Without the lock, both
        threads enter the critical section at the same time and
        `max_inside` reaches 2. With the lock, exactly one is inside
        at any moment.
        """
        import threading
        import time as _time

        from app.api.setup import _state_lock

        barrier = threading.Barrier(2)
        inside_count = [0]
        max_inside = [0]
        lock_for_counter = threading.Lock()

        def critical() -> None:
            barrier.wait()
            with _state_lock():
                with lock_for_counter:
                    inside_count[0] += 1
                    if inside_count[0] > max_inside[0]:
                        max_inside[0] = inside_count[0]
                _time.sleep(0.05)
                with lock_for_counter:
                    inside_count[0] -= 1

        t1 = threading.Thread(target=critical)
        t2 = threading.Thread(target=critical)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert max_inside[0] == 1, (
            f"REGRESSION: _state_lock allowed {max_inside[0]} "
            "concurrent threads inside critical section (expected 1). "
            "Two-admin TOCTOU is now reachable."
        )

    def test_state_lock_threaded_step_endpoints_one_winner(
        self, fresh_setup_state: Path
    ) -> None:
        """End-to-end thread-level race against the setup endpoints.

        Two real OS threads each call the FastAPI app via TestClient;
        one of them must observe `current_step=2` on read and return
        409 from `_ensure_step`. Pre-fix both would 200 and silently
        overwrite admin_credentials.json.
        """
        import threading
        from fastapi.testclient import TestClient

        from app.main import app

        barrier = threading.Barrier(2)
        results: list[int] = []
        results_lock = threading.Lock()

        def call(email: str) -> None:
            with TestClient(app) as c:
                barrier.wait()
                r = c.post(
                    "/v1/setup/step/admin",
                    json={"email": email, "password": "RacePass2026!"},
                )
                with results_lock:
                    results.append(r.status_code)

        t1 = threading.Thread(target=call, args=("alice@l22-thr.test",))
        t2 = threading.Thread(target=call, args=("bob@l22-thr.test",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert sorted(results) == [200, 409], (
            f"REGRESSION (threaded): expected one 200 + one "
            f"409, got {results}. Two-admin race-window is open."
        )

        # State must show single advance.
        state = json.loads(
            (fresh_setup_state / "setup_state.json").read_text(encoding="utf-8")
        )
        assert state["current_step"] == 2
        assert state["completed_steps"].count("admin") == 1
