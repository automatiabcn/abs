"""Q12 Session 7 R49 / L23 sweep 5 — billing_portal.py + marketplace.py.

Pre-R49: both routers had HTTPException raises with **zero**
emit_event coverage. The sweeps 1-4 progression covered me_account,
me_data_export, setup_admin, smart_link, beta_admin. Sweep 5 picks
up the remaining customer-facing money/ install paths:

  app/api/billing_portal.py — Stripe Customer Portal (/v1/billing/portal)
  app/api/marketplace.py    — plugin install / uninstall / lookup

Each silent raise becomes an emit_event(action, outcome, reason).
This file regression-pins the action taxonomy:

  billing.portal.create     {denied: stripe_not_configured, license_not_found}
                            {error:  stripe_error, portal_response_invalid}
                            {success: ...}
  marketplace.plugin.lookup {denied: plugin_not_found}
  marketplace.install       {denied: plugin_not_found, signature_invalid}
  marketplace.install.gate  {denied: cross_tenant_forbidden}
  marketplace.uninstall     {denied: not_installed}
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "backend" / "app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------- billing_portal.py ----------------------------------------------


class TestQ12L23Sweep5BillingPortal:
    src_path = APP / "api" / "billing_portal.py"

    @pytest.fixture(autouse=True)
    def _check_path(self) -> None:
        if not self.src_path.exists():
            pytest.skip(f"{self.src_path} missing on this build")

    def test_emit_event_imported(self) -> None:
        assert "from app.observability.audit import emit_event" in _read(
            self.src_path
        ), "billing_portal.py must import emit_event for audit coverage"

    def test_action_billing_portal_create_present(self) -> None:
        src = _read(self.src_path)
        # The 4 failure paths + 1 success path should all carry
        # action="billing.portal.create".
        assert src.count('action="billing.portal.create"') >= 4, (
            "billing_portal.py emit_event coverage regressed — "
            "expected ≥4 emits with action='billing.portal.create'"
        )

    @pytest.mark.parametrize(
        "reason",
        [
            "stripe_not_configured",
            "license_not_found",
            "stripe_error",
            "portal_response_invalid",
        ],
    )
    def test_taxonomy_reason_present(self, reason: str) -> None:
        src = _read(self.src_path)
        assert f'reason="{reason}"' in src, (
            f"billing_portal.py emit_event missing reason='{reason}'"
        )

    def test_success_outcome_present(self) -> None:
        src = _read(self.src_path)
        assert 'outcome="success"' in src, (
            "billing_portal.py emit_event missing the success-side audit"
        )


# ---------- marketplace.py -------------------------------------------------


class TestQ12L23Sweep5Marketplace:
    src_path = APP / "api" / "marketplace.py"

    @pytest.fixture(autouse=True)
    def _check_path(self) -> None:
        if not self.src_path.exists():
            pytest.skip(f"{self.src_path} missing on this build")

    def test_emit_event_imported(self) -> None:
        assert "from app.observability.audit import emit_event" in _read(
            self.src_path
        ), "marketplace.py must import emit_event for audit coverage"

    @pytest.mark.parametrize(
        "action",
        [
            "marketplace.plugin.lookup",
            "marketplace.install",
            "marketplace.install.gate",
            "marketplace.uninstall",
        ],
    )
    def test_action_taxonomy_present(self, action: str) -> None:
        src = _read(self.src_path)
        assert f'action="{action}"' in src, (
            f"marketplace.py emit_event missing action='{action}'"
        )

    @pytest.mark.parametrize(
        "reason",
        [
            "plugin_not_found",
            "signature_invalid",
            "cross_tenant_forbidden",
            "not_installed",
        ],
    )
    def test_taxonomy_reason_present(self, reason: str) -> None:
        src = _read(self.src_path)
        assert f'reason="{reason}"' in src, (
            f"marketplace.py emit_event missing reason='{reason}'"
        )
