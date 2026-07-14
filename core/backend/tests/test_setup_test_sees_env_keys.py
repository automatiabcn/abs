# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Step 6 has to test the server it is standing on, not the form it just showed.

The documented install path — the one the landing page's "Start free" button now
points at — configures providers in the compose `.env`. Those keys never pass
through the wizard's step 5. The connection test built its list from the wizard's
own state, so on that install it found nothing to ping, printed an empty result,
and the verdict on top of it said "No provider answered — chat will not be able
to answer a question yet" about a server whose chat answers fine.

The mirror-image bug is just as bad: `.env.example` ships `replace-with-...`
placeholders, and a naive "is this string non-empty" check counts one as a
configured provider and reports it to a brand-new customer as a red failure. The
cascade already knows better — `is_configured()` is what it uses when it decides
who to call — so the wizard asks it, instead of keeping a second opinion.
"""

from __future__ import annotations

from app.api import setup as setup_api


def test_a_key_from_the_environment_is_tested(monkeypatch):
    monkeypatch.setattr(setup_api.settings, "groq_api_key", "gsk_" + "a" * 40)

    from app.providers import cascade

    monkeypatch.setattr(cascade.settings, "groq_api_key", "gsk_" + "a" * 40)

    fields = _fields_under_test()
    assert "groq_api_key" in fields, (
        "a provider configured outside the wizard is invisible to the test that "
        "tells the customer whether chat can answer"
    )


def test_a_placeholder_from_env_example_is_not_a_provider(monkeypatch):
    from app.providers import cascade

    monkeypatch.setattr(cascade.settings, "cf_api_token", "replace-with-cf-api-token")
    monkeypatch.setattr(
        cascade.settings, "cf_account_id", "replace-with-cf-account-id"
    )
    monkeypatch.setattr(setup_api.settings, "cf_api_token", "replace-with-cf-api-token")

    assert "cf_api_token" not in _fields_under_test()


def _fields_under_test() -> list[str]:
    """The provider fields step 6 would ping, without making a network call."""
    from app.providers.cascade import is_configured

    return [
        field
        for field, provider in setup_api._FIELD_TO_PROVIDER.items()
        if is_configured(provider)
    ]
