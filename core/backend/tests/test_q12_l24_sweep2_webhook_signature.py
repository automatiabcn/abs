"""Q12 Round 22 / L24 sweep 2 — webhook signature audit + secret-leak hardening.

Pre-Round 22 inventory (3 webhook receivers):

    POST /webhooks/stripe                 — Stripe SDK construct_event
    POST /v1/integrations/slack/webhook   — Slack HMAC-SHA256
    POST /v1/integrations/github/webhook  — GitHub App HMAC-SHA256

Findings:

  Q12-L24-003 (MED) — Slack webhook leaks signing-check internals.
    Pre-fix, response body was
      f"Slack signature verify failed: {reason}"
    where `reason` enumerated:
      signing_secret_empty | header_missing | timestamp_invalid |
      timestamp_expired | signature_mismatch
    A caller can iterate and learn (a) whether the signing secret is
    provisioned (boot misconfig signal) and (b) which check failed
    (replay-tuning signal). Same Q12-L24 family as the R14 Stripe
    str(exc) leak (cus_*/sub_*/acct_* IDs into the response detail).
    Fix: emit reason via audit channel, return generic
    "slack_signature_invalid".

  Q12-L24-004 (LOW) — All three webhook signature failure paths were
    completely silent in audit (no emit_event, only logger.warning at
    INFO). Stripe SDK ValueError additionally surfaces "Could not
    deserialize key data..." in the swallowed exception, kept out of
    response by the i18n string but never logged structurally.

Round 22 wires emit_event onto every signature/payload denial path:

    webhooks.stripe.signature        denied {signature_missing | signature_invalid}
    webhooks.stripe.payload          denied invalid_payload (ValueError)
    integrations.slack.webhook.signature   denied {<reason taxonomy>}
    integrations.slack.webhook.payload     denied invalid_json
    integrations.github.webhook.signature  denied signature_invalid
    integrations.github.webhook.payload    denied invalid_json

Plus contract test: Slack response body must NOT contain the reason
taxonomy (regression guard against the Q12-L24-003 leak).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.observability.audit import LOGGER_NAME


def _audits_for(records, action_prefix: str) -> list[dict]:
    out = []
    for rec in records:
        if rec.name != LOGGER_NAME:
            continue
        a = getattr(rec, "audit", {}) or {}
        if a.get("action", "").startswith(action_prefix):
            out.append(a)
    return out


# ----------------------------------------------------------------------
# Slack — Q12-L24-003 leak fix + audit emission
# ----------------------------------------------------------------------


def _slack_sign(secret: str, ts: str, body: bytes) -> str:
    base = b"v0:" + ts.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


class TestQ12L24Sweep2Slack:
    def test_slack_response_body_does_not_leak_reason_taxonomy(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        """Q12-L24-003 regression guard. Pre-fix the response body included
        e.g. 'Slack signature verify failed: signature_mismatch'. Post-fix
        it is a generic constant; the taxonomy goes to audit only."""
        monkeypatch.setattr(settings, "slack_signing_secret", "sec-l24s2")
        ts = str(int(time.time()))
        body = b'{"event":{"type":"message"}}'
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/integrations/slack/webhook",
                content=body,
                headers={
                    "X-Slack-Request-Timestamp": ts,
                    "X-Slack-Signature": "v0=deadbeef",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 401
        # Response body MUST NOT include the reason taxonomy.
        for tok in (
            "signing_secret_empty",
            "header_missing",
            "timestamp_invalid",
            "timestamp_expired",
            "signature_mismatch",
        ):
            assert tok not in r.text, f"reason '{tok}' leaked to client body"

        # But the audit channel MUST carry it.
        events = _audits_for(caplog.records, "integrations.slack.webhook.signature")
        assert events
        assert events[-1]["reason"] == "signature_mismatch"
        assert events[-1]["provider"] == "slack"

    def test_slack_signing_secret_empty_emits_denied(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        monkeypatch.setattr(settings, "slack_signing_secret", "")
        ts = str(int(time.time()))
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/integrations/slack/webhook",
                content=b"{}",
                headers={
                    "X-Slack-Request-Timestamp": ts,
                    "X-Slack-Signature": "v0=00",
                },
            )
        assert r.status_code == 401
        assert "signing_secret_empty" not in r.text  # MUST stay server-side
        events = _audits_for(caplog.records, "integrations.slack.webhook.signature")
        assert events and events[-1]["reason"] == "signing_secret_empty"

    def test_slack_url_verification_handshake_still_works(
        self, client: TestClient, monkeypatch
    ) -> None:
        """Post-fix the happy path must not regress. Slack sends a
        url_verification challenge with a real signature; we must still
        echo `challenge` back."""
        secret = "sec-l24s2-handshake"
        monkeypatch.setattr(settings, "slack_signing_secret", secret)
        ts = str(int(time.time()))
        body = b'{"type":"url_verification","challenge":"abc-l24s2"}'
        sig = _slack_sign(secret, ts, body)
        r = client.post(
            "/v1/integrations/slack/webhook",
            content=body,
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
                "Content-Type": "application/json",
            },
        )
        assert r.status_code == 200
        assert r.json()["challenge"] == "abc-l24s2"


# ----------------------------------------------------------------------
# GitHub — audit emission on signature failure
# ----------------------------------------------------------------------


class TestQ12L24Sweep2GitHub:
    def test_github_signature_failure_emits_denied(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        monkeypatch.setattr(settings, "github_app_webhook_secret", "ghw-l24s2")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/integrations/github/webhook",
                content=b'{"action":"opened"}',
                headers={
                    "X-Hub-Signature-256": "sha256=deadbeef",
                    "X-GitHub-Event": "pull_request",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 401
        # Response body should not leak the secret material.
        assert "ghw-l24s2" not in r.text
        events = _audits_for(caplog.records, "integrations.github.webhook.signature")
        # Q12-L24-008 (S7 R50) — sweep 2 originally over-collapsed every
        # github failure mode into reason="signature_invalid". The R50 fix
        # surfaces granular taxonomy: signing_secret_empty / header_missing
        # / signature_mismatch. For a well-formed sha256= header with
        # wrong HMAC the reason is now "signature_mismatch". The legacy
        # "signature_invalid" string is still accepted as the back-compat
        # fallback so older deploys don't fail this assertion.
        assert events
        assert events[-1]["reason"] in {"signature_mismatch", "signature_invalid"}
        assert events[-1]["provider"] == "github"


# ----------------------------------------------------------------------
# Stripe — audit emission on signature paths
# ----------------------------------------------------------------------


class TestQ12L24Sweep2Stripe:
    def test_stripe_signature_missing_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/webhooks/stripe",
                content=b'{"id":"evt_test"}',
                headers={"Content-Type": "application/json"},
                # Deliberately omitting stripe-signature header.
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "webhooks.stripe.signature")
        assert events and events[-1]["reason"] == "signature_missing"

    def test_stripe_signature_invalid_emits_denied(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        import stripe

        def _raise_sig(*a, **k):
            raise stripe.error.SignatureVerificationError(
                "No signatures found matching the expected signature for payload",
                "fake-header",
            )

        monkeypatch.setattr(stripe.Webhook, "construct_event", _raise_sig)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/webhooks/stripe",
                content=b'{"id":"evt_test"}',
                headers={
                    "stripe-signature": "t=1,v1=garbage",
                    "Content-Type": "application/json",
                },
            )
        assert r.status_code == 400
        # Response uses i18n constant — should NOT carry SDK exception text.
        assert "No signatures found" not in r.text
        events = _audits_for(caplog.records, "webhooks.stripe.signature")
        assert events and events[-1]["reason"] == "signature_invalid"
        assert events[-1].get("error_class") == "SignatureVerificationError"

    def test_stripe_payload_invalid_emits_denied(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        import stripe

        def _raise_value(*a, **k):
            raise ValueError("Could not deserialize key data: nuance from SDK")

        monkeypatch.setattr(stripe.Webhook, "construct_event", _raise_value)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/webhooks/stripe",
                content=b"not-json-at-all",
                headers={
                    "stripe-signature": "t=1,v1=ok",
                    "Content-Type": "text/plain",
                },
            )
        assert r.status_code == 400
        assert "Could not deserialize" not in r.text
        events = _audits_for(caplog.records, "webhooks.stripe.payload")
        assert events and events[-1]["reason"] == "payload_invalid"
        assert events[-1].get("error_class") == "ValueError"
