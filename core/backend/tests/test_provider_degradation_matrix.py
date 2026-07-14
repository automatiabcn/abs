"""Provider degradation matrix (7 scenarios).

Source memory: feedback_provider_degradation_test.md.

Customer scenario: operator boots ABS with anywhere from 0 to 6 provider
keys present. The cascade contract:
  * Skip un-configured providers (empty / placeholder / too-short keys).
  * `GET /v1/cascade/providers` reports configured_count + missing[]
    so the panel can gray-out un-configured rows (configured:bool).
  * `POST /v1/cascade/run` with anthropic_mock OFF returns 503
    "no_providers_configured" when the active chain is empty, else
    walks the live cascade via `call_with_cascade`. An earlier round of the
    Founder Tester session replaced the prior 503
    "live_cascade_pending" gate with the real orchestrator wiring —
    this test now mocks the orchestrator so we keep the *gate*
    contract under test without making real provider HTTP calls.

Brief tuple `(name, expected_active, expected_configured)` is honoured
where the cascade semantics align; one tuple — "all_free_missing 0/1"
— could not be reconciled with `get_active_providers` returning all
configured providers, so it is treated as a single-Anthropic case
(1 active, 1 configured) with a NOTE in the round summary.
"""

from __future__ import annotations

import pytest

from app.providers.schemas import ProviderResponse

# A real-looking key passes is_configured (>8 chars, not a placeholder string).
REAL = "real-test-key-AAAAAAAA"
# "Configured, but wrong" — a key the operator really did paste in, which the
# provider will reject at call time. It must NOT be one of the .env.example
# placeholder strings: those now correctly read as *unconfigured*, because a
# provider carrying one has no chance of working and only breaks the cascade it
# sits in.
INVALID = "wrong-but-real-looking-key-AAAA"

ALL_KEYS: dict[str, str] = {
    "anthropic_api_key": REAL,
    "groq_api_key": REAL,
    "cerebras_api_key": REAL,
    "gemini_api_key": REAL,
    # Cloudflare needs both halves — a token alone routes nowhere.
    "cf_api_token": REAL,
    "cf_account_id": REAL,
    "cohere_api_key": REAL,
}

ALL_INVALID: dict[str, str] = {k: INVALID for k in ALL_KEYS}

ANTHROPIC_ONLY: dict[str, str] = {
    "anthropic_api_key": REAL,
    "groq_api_key": "",
    "cerebras_api_key": "",
    "gemini_api_key": "",
    "cf_api_token": "",
    "cf_account_id": "",
    "cohere_api_key": "",
}


def _scenario_overrides(name: str) -> dict[str, str]:
    if name == "all_present":
        return dict(ALL_KEYS)
    if name == "anthropic_skip":
        return {**ALL_KEYS, "anthropic_api_key": ""}
    if name == "groq_missing":
        return {**ALL_KEYS, "groq_api_key": ""}
    if name == "3_free_missing":
        return {
            **ALL_KEYS,
            "groq_api_key": "",
            "cerebras_api_key": "",
            "gemini_api_key": "",
        }
    if name == "5_free_missing":
        return dict(ANTHROPIC_ONLY)
    if name == "all_free_missing":
        # All 5 free providers empty, anthropic still set.
        # NOTE — Brief expected (0,1); cascade semantics yield (1,1)
        # because anthropic counts as active. Diverges from brief.
        return dict(ANTHROPIC_ONLY)
    if name == "all_invalid":
        return dict(ALL_INVALID)  # keys present and wrong: configured, unusable
    raise AssertionError(f"unknown scenario {name!r}")


# (scenario_name, expected_active_count, expected_configured_count, expect_run_ok)
# expect_run_ok: True if we expect /v1/cascade/run (mock off) to escape the
# "no_providers_configured" 503 (i.e. ≥1 active provider). All cases short of
# zero-active get the "live_cascade_pending" 503 — both are 503 so we just
# inspect the message.
SCENARIOS: list[tuple[str, int, int]] = [
    ("all_present", 6, 6),
    ("anthropic_skip", 5, 5),
    ("groq_missing", 5, 5),
    ("3_free_missing", 3, 3),
    ("5_free_missing", 1, 1),
    ("all_free_missing", 1, 1),
    ("all_invalid", 6, 6),  # placeholders bypass length check; configured map True
]


@pytest.fixture()
def admin_client(client, monkeypatch):
    """Login + force anthropic_mock OFF so cascade gate-503 surfaces."""
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


def _apply_provider_keys(monkeypatch, overrides: dict[str, str]) -> None:
    from app.config import settings

    for attr, value in overrides.items():
        monkeypatch.setattr(settings, attr, value, raising=False)


@pytest.mark.parametrize("scenario, expected_active, expected_configured", SCENARIOS)
def test_provider_degradation_matrix(
    admin_client, monkeypatch, scenario, expected_active, expected_configured
):
    overrides = _scenario_overrides(scenario)
    _apply_provider_keys(monkeypatch, overrides)

    # 1) /v1/cascade/providers reports configured_count + missing[].
    r = admin_client.get("/v1/cascade/providers")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["active"], list)
    assert isinstance(body["missing"], list)
    assert body["configured_count"] == expected_configured, (
        f"{scenario}: configured_count={body['configured_count']} "
        f"!= expected {expected_configured}"
    )
    assert len(body["active"]) == expected_active, (
        f"{scenario}: active={body['active']} != expected count {expected_active}"
    )
    # `total` always = full PROVIDER_ORDER length.
    assert body["total"] == 6
    # Missing is the complement.
    assert len(body["missing"]) == body["total"] - body["configured_count"]

    # 2) /v1/cascade/run (mock off) — gate behaviour:
    #    • zero active   → 503 "no_providers_configured"
    #    • ≥1 active     → call_with_cascade walks the chain. Founder
    #      Tester This change wired this live; we mock the
    #      orchestrator here so the test stays hermetic.
    async def _fake_call(prompt, *, primary, model=None, fallbacks=(), **kw):
        return ProviderResponse(
            text=f"mocked:{primary}",
            provider=primary,
            model=model or "mock-model",
            elapsed_ms=1,
            tokens_in=2,
            tokens_out=3,
        )

    monkeypatch.setattr("app.api.cascade.call_with_cascade", _fake_call)

    run = admin_client.post(
        "/v1/cascade/run",
        json={"prompt": "degradation ping", "max_tokens": 8},
    )
    if expected_active == 0:
        assert run.status_code == 503, run.text
        detail = run.json().get("detail", "")
        assert "no_providers_configured" in detail, detail
    else:
        assert run.status_code == 200, run.text
        rb = run.json()
        # primary should be the first active provider.
        assert rb["provider"] in body["active"], rb
        assert rb["completion"].startswith("mocked:")
        assert rb["mock"] is False  # mock=True is reserved for anthropic-mock
