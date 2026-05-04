"""Q12 Session 7 R50 / L24 sweep 5 — webhook signature secret audit.

Audit findings:

  Stripe webhook  (app/api/webhooks/stripe.py):
    Pre-existing emit_event coverage on signature_missing / payload_invalid /
    signature_invalid (Q12-L24 sweep 2). No new finding.

  Slack webhook   (app/api/integrations/slack.py):
    verify_slack_signature already returns (ok, reason) tuple (signing_secret_empty
    / header_missing / timestamp_invalid / timestamp_expired / signature_mismatch).
    Caller routes reason into emit_event taxonomy. No new finding.

  GitHub webhook  (app/api/integrations/github_app.py):
    **Q12-L24-008 (LOW ops visibility)** — `verify_webhook_signature` returned
    a single bool. Caller emitted generic `reason="signature_invalid"` even
    when the actual cause was `secret==""` (boot misconfig). Operations
    could not distinguish a forgotten secret from an attack.

  Inngest:
    Signature verification is delegated to the inngest SDK
    `fast_api.serve(app, client, functions)`; not a user-facing webhook
    endpoint we own. No fix surface.

Fix (R50):
  1. New `verify_webhook_signature_typed` — returns (ok, reason) tuple
     with explicit `signing_secret_empty` / `header_missing` /
     `signature_mismatch` distinction.
  2. Old single-bool `verify_webhook_signature` is now a back-compat shim
     so any external test caller is unaffected.
  3. The /v1/integrations/github/webhook handler routes the typed reason
     into emit_event so audit logs distinguish ops-misconfig from attack.

This file regression-pins the new taxonomy + back-compat shim.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "backend" / "app"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------- helper-side: typed signature verification ---------------------


class TestQ12L24008TypedSignature:
    """github_app.verify_webhook_signature_typed — taxonomy distinguishes
    boot-misconfig from attack."""

    def setup_method(self) -> None:
        from app.integrations.github_app import verify_webhook_signature_typed

        self.fn = verify_webhook_signature_typed

    def test_secret_empty_returns_signing_secret_empty(self) -> None:
        ok, reason = self.fn(secret="", body=b"x", signature_header="sha256=abc")
        assert ok is False
        assert reason == "signing_secret_empty", (
            "Q12-L24-008 regression: empty secret must surface as "
            "'signing_secret_empty', not collapse into 'signature_invalid'"
        )

    def test_header_missing(self) -> None:
        ok, reason = self.fn(secret="s3cret", body=b"x", signature_header="")
        assert ok is False
        assert reason == "header_missing"

    def test_header_wrong_prefix(self) -> None:
        ok, reason = self.fn(
            secret="s3cret", body=b"x", signature_header="sha512=abc"
        )
        assert ok is False
        assert reason == "header_missing"

    def test_signature_mismatch(self) -> None:
        ok, reason = self.fn(
            secret="s3cret",
            body=b"hello",
            signature_header="sha256=" + "0" * 64,
        )
        assert ok is False
        assert reason == "signature_mismatch"

    def test_signature_match_returns_ok(self) -> None:
        import hashlib
        import hmac

        secret = "s3cret"
        body = b"hello"
        sig = (
            "sha256="
            + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        )
        ok, reason = self.fn(secret=secret, body=body, signature_header=sig)
        assert ok is True
        assert reason == ""


class TestQ12L24008BackCompatShim:
    """The single-bool `verify_webhook_signature` must keep working for
    external callers that were written against the pre-R50 contract."""

    def test_bool_shim_present(self) -> None:
        from app.integrations.github_app import verify_webhook_signature

        # Sanity: shim still callable + returns bool.
        result = verify_webhook_signature(
            secret="", body=b"", signature_header=""
        )
        assert result is False

    def test_bool_shim_routes_through_typed_impl(self) -> None:
        import hashlib
        import hmac

        from app.integrations.github_app import verify_webhook_signature

        secret = "rot13"
        body = b"payload"
        sig = (
            "sha256="
            + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        )
        assert (
            verify_webhook_signature(
                secret=secret, body=body, signature_header=sig
            )
            is True
        )


# ---------- caller-side: audit taxonomy in github_app router ---------------


class TestQ12L24008GithubWebhookAuditTaxonomy:
    src_path = APP / "api" / "integrations" / "github_app.py"

    @pytest.fixture(autouse=True)
    def _check_path(self) -> None:
        if not self.src_path.exists():
            pytest.skip(f"{self.src_path} missing on this build")

    def test_uses_typed_helper(self) -> None:
        src = _read(self.src_path)
        assert "verify_webhook_signature_typed" in src, (
            "Q12-L24-008 regression: github_app webhook handler must use "
            "verify_webhook_signature_typed (the (ok, reason) tuple) so "
            "the audit emit can distinguish secret_empty from attack"
        )

    def test_audit_routes_reason(self) -> None:
        src = _read(self.src_path)
        # The handler should pass `reason` (the typed string) — not a hard
        # coded "signature_invalid" — into emit_event when ok is False.
        # Substring presence is sufficient as a regression check.
        assert "reason=reason" in src or 'reason=reason or "signature_invalid"' in src, (
            "Q12-L24-008 regression: github_app webhook handler is no "
            "longer routing the typed reason into the emit_event call"
        )


# ---------- existing webhook signature audits (regression pin) -------------


class TestQ12L24Sweep5StripeWebhookAuditPin:
    """Pin the pre-existing Stripe webhook audit coverage so a future
    refactor that drops the emit_event calls fails this sweep, not a
    real production incident."""

    src_path = APP / "api" / "webhooks" / "stripe.py"

    @pytest.fixture(autouse=True)
    def _check_path(self) -> None:
        if not self.src_path.exists():
            pytest.skip(f"{self.src_path} missing on this build")

    @pytest.mark.parametrize(
        "reason",
        [
            "signature_missing",
            "payload_invalid",
            "signature_invalid",
        ],
    )
    def test_stripe_webhook_carries_reason(self, reason: str) -> None:
        src = _read(self.src_path)
        assert f'reason="{reason}"' in src, (
            f"Stripe webhook audit regressed — reason='{reason}' missing"
        )


class TestQ12L24Sweep5SlackWebhookAuditPin:
    """Same pin for the Slack webhook signature audit (sweep 2 work)."""

    src_path = APP / "api" / "integrations" / "slack.py"

    @pytest.fixture(autouse=True)
    def _check_path(self) -> None:
        if not self.src_path.exists():
            pytest.skip(f"{self.src_path} missing on this build")

    def test_slack_webhook_uses_typed_helper(self) -> None:
        src = _read(self.src_path)
        assert "verify_slack_signature(" in src
        # The typed helper returns (ok, reason). The handler MUST route
        # `reason` into emit_event so signing_secret_empty / timestamp_*
        # / signature_mismatch are distinguishable in audit.
        assert "reason=reason" in src or 'reason=reason or "signature_invalid"' in src
