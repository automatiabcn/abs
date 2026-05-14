"""Sprint 2N FAZ C — Customer compose Postgres + RLS integration check (P0 #2M-026).

Compose dosyasının schema'sı (Postgres service + backend env + volume),
entrypoint.sh'in alembic upgrade akışı ve .env.example'da ABS_DB_PASSWORD
zorunluluğu test edilir. Postgres engine'i gerçekten ayağa kaldırmıyor;
amaç customer paketinin Sprint 2K RLS migration'ı için gerekli tüm
parçalarının yerinde olduğunu CI'da doğrulamak.

Sprint 2M bug log: #2M-026
"""
from __future__ import annotations

import pathlib

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]

COMPOSE = REPO_ROOT / "infra" / "docker-compose.customer.yml"
ENTRYPOINT = BACKEND_ROOT / "scripts" / "entrypoint.sh"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _load_compose() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(COMPOSE.read_text())


def test_customer_compose_has_postgres_service() -> None:
    cfg = _load_compose()
    assert "postgres" in cfg["services"], (
        "customer compose must declare a `postgres` service "
        "(Sprint 2N FAZ C — Sprint 2K RLS is no-op on SQLite)"
    )
    pg = cfg["services"]["postgres"]
    assert pg["image"].startswith("postgres:16"), (
        f"expected postgres:16-alpine, got {pg['image']}"
    )
    # Healthcheck so backend depends_on service_healthy is meaningful.
    assert "healthcheck" in pg
    assert "pg_isready" in str(pg["healthcheck"])
    # Named volume for persistence.
    assert any(
        "abs-postgres-data" in str(v) for v in pg.get("volumes", [])
    ), "postgres data must persist in abs-postgres-data volume"


def test_customer_compose_backend_depends_on_postgres_healthy() -> None:
    cfg = _load_compose()
    deps = cfg["services"]["backend"]["depends_on"]
    assert "postgres" in deps, (
        "backend must depend on postgres so alembic upgrade head sees "
        "a ready DB before serving traffic"
    )
    assert deps["postgres"]["condition"] == "service_healthy"


def test_customer_compose_backend_defaults_to_postgres_url() -> None:
    cfg = _load_compose()
    env = cfg["services"]["backend"]["environment"]
    db_url = str(env.get("ABS_DATABASE_URL", ""))
    assert "postgresql+psycopg" in db_url, (
        f"backend must default to postgres+psycopg, got: {db_url}"
    )
    assert "postgres:5432" in db_url and "abs" in db_url
    # ${ABS_DB_PASSWORD} substitution preserved (no hardcoded password).
    assert "${ABS_DB_PASSWORD}" in db_url


def test_customer_compose_postgres_password_required_via_env() -> None:
    """`${ABS_DB_PASSWORD:?...}` syntax must force boot failure when unset."""
    raw = COMPOSE.read_text()
    assert "ABS_DB_PASSWORD:?" in raw, (
        "ABS_DB_PASSWORD must use the `${VAR:?error}` form so missing it "
        "fails fast (no silent fallback to a default password)"
    )


def test_customer_compose_postgres_data_volume_declared() -> None:
    cfg = _load_compose()
    assert "abs-postgres-data" in cfg.get("volumes", {}), (
        "abs-postgres-data named volume must be declared so docker tracks it"
    )


def test_entrypoint_runs_alembic_upgrade_on_postgres() -> None:
    raw = ENTRYPOINT.read_text()
    assert "alembic upgrade head" in raw, (
        "entrypoint.sh must run `alembic upgrade head` before launching "
        "uvicorn (Sprint 2N FAZ C — Sprint 2K RLS migration application)"
    )
    # Postgres branch executes alembic.
    assert "postgresql*" in raw or "postgres*" in raw
    # SQLite branch skips alembic (legacy single-tenant).
    assert "sqlite*" in raw


def test_entrypoint_alembic_failure_exits_nonzero() -> None:
    raw = ENTRYPOINT.read_text()
    # The Postgres branch must exit non-zero on failure — refusing to
    # start with stale schema, not silently fall back to SQLite.
    assert "exit 1" in raw, (
        "entrypoint must refuse to start when alembic upgrade head fails"
    )


def test_env_example_documents_abs_db_password() -> None:
    raw = ENV_EXAMPLE.read_text()
    assert "ABS_DB_PASSWORD" in raw, (
        ".env.example must include ABS_DB_PASSWORD so customers know "
        "to generate one (Sprint 2N onwards)"
    )
    # Generation recipe is documented.
    assert "openssl rand -base64 32" in raw
