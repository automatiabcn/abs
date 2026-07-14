"""MT Phase 1 — BYOK end-to-end wiring (#1 callers, #6 activation, #4 cache)."""

from __future__ import annotations


from app.cascade.cache import prompt_hash
from app.multitenant import provider_keys as pk
from app.providers.cascade import get_active_providers


# ── #4 cache key owner-scoping ───────────────────────────────────────────────


def test_cache_key_owner_namespaced():
    base = prompt_hash("hi", "m", tenant_id="t1")
    u = prompt_hash("hi", "m", tenant_id="t1", owner="u:a@x.com")
    v = prompt_hash("hi", "m", tenant_id="t1", owner="u:b@x.com")
    assert base != u != v
    assert u != v  # different owners → different cache namespaces
    # empty owner keeps the legacy tenant-only key (backward-compatible)
    assert prompt_hash("hi", "m", tenant_id="t1", owner="") == base


# ── #6 tenant-aware activation ───────────────────────────────────────────────


def test_extra_configured_activates_provider(monkeypatch):
    # The point of the test is what `extra_configured` does when the operator has
    # NOT configured groq globally. It used to read that premise off the ambient
    # environment, so on any machine with a real GROQ_API_KEY in .env — a
    # developer's, or a customer's — the suite went red on a product that was
    # working perfectly. State the premise instead of hoping for it.
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "", raising=False)

    # With no global key, groq is not active...
    assert "groq" not in get_active_providers()
    # ...but a per-owner key (extra_configured) activates it.
    assert "groq" in get_active_providers(extra_configured=frozenset({"groq"}))


def test_tenant_configured_providers_reports_db_keys(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "provider_key_encryption_key", "k", raising=False)
    pk.set_provider_key(
        tenant_slug="byok-t",
        owner_type="user",
        owner_id="dev@x.com",
        provider="cerebras",
        value="ce-user-key",
    )
    got = pk.tenant_configured_providers(tenant_slug="byok-t", user_subject="dev@x.com")
    assert "cerebras" in got
    # a different user in the same tenant sees nothing
    assert (
        pk.tenant_configured_providers(tenant_slug="byok-t", user_subject="other@x.com")
        == set()
    )


def test_byok_provider_enters_cascade_chain(monkeypatch):
    """End-to-end #6: a provider configured ONLY via a per-user key is selected
    into the active chain (would previously be invisible)."""
    from app.config import settings

    monkeypatch.setattr(settings, "provider_key_encryption_key", "k", raising=False)
    pk.set_provider_key(
        tenant_slug="byok-chain",
        owner_type="user",
        owner_id="u@x.com",
        provider="cohere",
        value="co-user-key",
    )
    extra = frozenset(
        pk.tenant_configured_providers(tenant_slug="byok-chain", user_subject="u@x.com")
    )
    chain = get_active_providers(extra_configured=extra)
    assert "cohere" in chain
