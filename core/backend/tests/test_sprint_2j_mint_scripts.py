"""Sprint 2J FAZ E — guardrails for mint_and_email.sh + customer_onboard.sh.

These two shell scripts are the only path a customer's license JWT
travels through, so a silent regression (e.g. someone removes
`--dry-run`, or the JTI grep stops matching the JWT payload) would
break Pilot Batch 1 broadcast before anyone notices. The FAZ A
preflight log shows the `--dry-run` flag was used as recently as
2026-05-09; this test ensures it stays wired even after future
refactors.

What we assert:

* `scripts/mint_and_email.sh` accepts and advertises `--dry-run`
  alongside its three required positional arguments, and the
  POST-side bypass still routes through `https://api.resend.com/emails`
  (so a typo on the Resend host can't slip past code review).
* `scripts/customer_onboard.sh` materialises a JWT with a
  base64-decodable middle segment whose payload contains the four
  claims the operator playbook documents: `customer_id`, `tier`,
  `seat_count`, and `jti`. No live network call required — the
  script runs synchronously and writes `customer-keys/<slug>/license.jwt`.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

# mint_and_email.sh + customer_onboard.sh are founder-only ops tooling and are
# .gitignored (see repo .gitignore "Founder-only ops tooling"). They exist on
# the operator host but never in a clean checkout, so this guardrail module is
# skipped wherever they're absent (CI / fresh clone) instead of hard-failing.
pytestmark = pytest.mark.skipif(
    not (_REPO_ROOT / "scripts" / "mint_and_email.sh").exists()
    or not (_REPO_ROOT / "scripts" / "customer_onboard.sh").exists(),
    reason="founder-only ops scripts (gitignored); present only on the operator host",
)


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def test_mint_and_email_advertises_dry_run_flag():
    text = _read("scripts/mint_and_email.sh")
    # The flag is the only way to exercise the script in CI/worker
    # contexts without burning a Resend send. Both the help blurb and
    # the actual handling block must mention it so a refactor doesn't
    # silently drop one half.
    assert "--dry-run" in text, "mint_and_email.sh must keep --dry-run"
    assert "DRY RUN" in text or "dry_run" in text


def test_mint_and_email_targets_resend_endpoint():
    # FAZ E — guard against silent endpoint drift. The script is the
    # only place the prod Resend host is hard-coded; if someone moves
    # the constant or typos the path, customer emails go to /dev/null
    # without an error.
    text = _read("scripts/mint_and_email.sh")
    assert "api.resend.com/emails" in text


@pytest.mark.skipif(
    not (_REPO_ROOT / "scripts" / "customer_onboard.sh").is_file(),
    reason="customer_onboard.sh not bundled in this checkout",
)
def test_customer_onboard_mints_jwt_with_extractable_jti():
    # FAZ E — exercise the real script end-to-end on a throwaway slug,
    # decode the middle JWT segment, and confirm the four claims the
    # operator playbook (FOUNDER_ITER3_LIVE_DISPATCH.md §1.4) tells
    # founders to verify before sending a license. The slug is cleaned
    # up afterwards so no `customer-keys/abs2jcheck-*` debris lingers.
    slug_email = "abs-2j-check@test.invalid"
    customer_label = "Abs2jCheck"
    res = subprocess.run(
        [
            "bash",
            str(_REPO_ROOT / "scripts" / "customer_onboard.sh"),
            customer_label,
            slug_email,
            "self-host",
            "1",
            "30",
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        assert res.returncode == 0, (
            f"customer_onboard.sh failed: stderr={res.stderr!r} stdout={res.stdout!r}"
        )

        keys_dir = _REPO_ROOT / "customer-keys"
        candidates = sorted(
            p for p in keys_dir.iterdir() if p.name.startswith("abs2jcheck")
        )
        assert candidates, f"no abs2jcheck-* slug under {keys_dir}"
        slug_dir = candidates[-1]

        jwt = (slug_dir / "license.jwt").read_text(encoding="utf-8").strip()
        # Decode the payload segment (PyJWT not needed — we don't
        # validate the signature here, only the claim shape).
        parts = jwt.split(".")
        assert len(parts) == 3, f"expected 3-segment JWT, got {len(parts)}"
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        for claim in ("customer_id", "tier", "seat_count", "jti", "iat", "exp"):
            assert claim in payload, f"missing claim: {claim}"
        assert payload["tier"] == "self-host"
        assert payload["seat_count"] == 1
        assert payload["customer_id"] == slug_email
        # jti is a 32-char hex string (Python uuid4().hex shape).
        assert isinstance(payload["jti"], str) and len(payload["jti"]) == 32
    finally:
        # Cleanup whatever slug the script created so future test runs
        # are deterministic + customer-keys/ doesn't bloat.
        keys_dir = _REPO_ROOT / "customer-keys"
        if keys_dir.is_dir():
            for stale in keys_dir.glob("abs2jcheck*"):
                if stale.is_dir():
                    shutil.rmtree(stale, ignore_errors=True)
