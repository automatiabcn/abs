# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Billing round — POST /v1/billing/portal must be rate-limited.

The portal endpoint is public (the landing "Manage" modal posts an email and
gets a Stripe customer-portal URL). checkout/create-session already carries
@limiter.limit("10/minute"); the portal did NOT, leaving it open to bulk abuse
/ email-enumeration against the vendor's Stripe account. This pins parity.

NOTE (documented for founder): rate-limiting throttles abuse but does not close
the deeper gap — the flow returns a portal session for ANY submitted email with
no proof of ownership. Closing that needs an email-magic-link (send the portal
link to the address) or a logged-in session; that is a product/UX change.
"""

from __future__ import annotations


def test_portal_is_rate_limited(client):
    """The 11th call within the window is throttled (10/minute).

    What the call *returns* is not this test's business, and pinning it down was
    making the test depend on the order the suite happens to run in: `conftest`
    assigns `settings.stripe_secret_key = "sk_test_dummy"` without monkeypatch, so
    whether the portal short-circuits to 503 (no key) or reaches Stripe and comes
    back 502 (bad key) depends on whether some earlier file has already pulled the
    `client` fixture in. The limiter runs before any of that, which is the whole
    claim here."""
    body = {"customer_email": "buyer@example.com", "return_url": "https://x/"}
    seen_429 = False
    for _ in range(12):
        r = client.post("/v1/billing/portal", json=body)
        if r.status_code == 429:
            seen_429 = True
            break
        assert r.status_code != 200, "the portal answered without a real Stripe key"
    assert seen_429, "portal endpoint should 429 after exceeding 10/minute"
