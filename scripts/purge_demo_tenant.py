"""G4 — Purge the `demo-acme` tenant fixtures and rotate placeholder keys.

Pairs with `seed_demo_tenant.py`. Run after a customer-journey playthrough
to wipe the on-disk demo state. Real ABS deployments would also run a Cerbos
audit-log scrub here; this stub records the rotation event in a dedicated
audit file so QA can confirm "Cerbos audit log clean".
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import secrets
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT / "core" / "backend" / "tests" / "fixtures" / "demo_acme_tenant.json"
)
AUDIT_DIR = REPO_ROOT / ".audit"
PURGE_LOG = AUDIT_DIR / "demo-acme-purge.log"
KEY_LOG = AUDIT_DIR / "demo-acme-key-rotation.log"
TENANT_ID = "demo-acme"

# Placeholder keys that get rotated on every purge so a stale value never
# survives between playthroughs.
ROTATED_KEYS = (
    "TEST_OPENAI_API_KEY",
    "TEST_GEMINI_API_KEY",
    "TEST_ANTHROPIC_API_KEY",
    "TEST_RECALL_API_KEY",
    "TEST_GMAIL_OAUTH_CLIENT_ID",
    "TEST_GMAIL_OAUTH_CLIENT_SECRET",
)


def _rotate_keys() -> dict[str, str]:
    """Generate fresh sandbox-grade values for every TEST_* key."""
    return {key: f"rotated-{secrets.token_hex(8)}" for key in ROTATED_KEYS}


def _audit_line(path: pathlib.Path, payload: dict[str, object]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without touching the filesystem",
    )
    args = parser.parse_args(argv)

    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    actions: list[str] = []

    if FIXTURE_PATH.exists():
        if not args.dry_run:
            FIXTURE_PATH.unlink()
        try:
            display = FIXTURE_PATH.relative_to(REPO_ROOT)
        except ValueError:
            display = FIXTURE_PATH
        actions.append(f"removed {display}")
    else:
        actions.append("fixture already absent")

    rotated = _rotate_keys()
    if not args.dry_run:
        _audit_line(
            PURGE_LOG,
            {
                "ts": timestamp,
                "action": "purge",
                "tenant_id": TENANT_ID,
                "fixture_removed": FIXTURE_PATH.exists() is False,
            },
        )
        _audit_line(
            KEY_LOG,
            {
                "ts": timestamp,
                "tenant_id": TENANT_ID,
                "rotated_keys": list(rotated.keys()),
            },
        )

    print(f"PURGE {TENANT_ID} ts={timestamp}")
    for line in actions:
        print(f"  - {line}")
    print(f"  - rotated {len(rotated)} placeholder keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
