# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Consent Ledger — set/get + the fail-closed channel gate."""

from __future__ import annotations

from datetime import datetime, timezone

from app.consent import check_channel, get_consent, set_consent


def test_gate_fail_closed_without_record() -> None:
    g = check_channel(tenant_slug="tC", contact_email="nobody@x.io", channel="email")
    assert g["allowed"] is False
    assert g["reason"] == "no_consent_on_file"


def test_set_and_channel_allow() -> None:
    rec = set_consent(
        tenant_slug="tC", contact_email="Musteri@X.io", email_consent=True,
        opt_in_source="web_form", legal_basis="consent",
    )
    assert "email" in rec["allowed_channels"]
    # email normalized to lower
    assert get_consent(tenant_slug="tC", contact_email="musteri@x.io") is not None
    g = check_channel(tenant_slug="tC", contact_email="musteri@x.io", channel="email")
    assert g["allowed"] is True and g["status"] == "opt-in"
    # a non-consented channel stays blocked
    assert check_channel(tenant_slug="tC", contact_email="musteri@x.io", channel="whatsapp")["allowed"] is False


def test_do_not_call_blocks_phone() -> None:
    set_consent(tenant_slug="tC", contact_email="dnc@x.io", phone_consent=True, do_not_call=True)
    g = check_channel(tenant_slug="tC", contact_email="dnc@x.io", channel="phone")
    assert g["allowed"] is False and g["reason"] == "do_not_call"


def test_opt_out_blocks_all() -> None:
    set_consent(tenant_slug="tC", contact_email="out@x.io", email_consent=True,
                opt_out_at=datetime.now(timezone.utc))
    g = check_channel(tenant_slug="tC", contact_email="out@x.io", channel="email")
    assert g["allowed"] is False and g["reason"] == "opted_out"


def test_unknown_channel() -> None:
    assert check_channel(tenant_slug="tC", contact_email="x@x.io", channel="carrierpigeon")["allowed"] is False


def test_tenant_isolation() -> None:
    set_consent(tenant_slug="tCa", contact_email="shared@x.io", email_consent=True)
    # other tenant has no record for the same email
    assert get_consent(tenant_slug="tCb", contact_email="shared@x.io") is None
    assert check_channel(tenant_slug="tCb", contact_email="shared@x.io", channel="email")["allowed"] is False
