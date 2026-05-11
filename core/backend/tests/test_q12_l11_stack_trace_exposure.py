# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 2D ITEM-2.3 — CodeQL py/stack-trace-exposure regression tests.

Three alerts:
  - #46 core/backend/app/api/admin/providers_save.py:245 (last_test.error)
  - #12 core/backend/app/api/update.py:39   (changelog error branch)
  - #13 core/backend/app/api/update.py:47   (changelog happy path data flow)

Fix pattern: opaque `request_id`-style error code, full trace logged
server-side, never echoed to caller.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------- providers_save._live_test_provider (#46) -----------------------


@pytest.mark.asyncio
async def test_live_test_provider_generic_exception_returns_request_id():
    from app.api.admin import providers_save as mod

    with patch.object(mod, "_PROVIDER_RUNTIME_NAME", {"x": "x"}):
        # Force call_with_cascade to raise an arbitrary exception with stack content
        async def _raise(*_a, **_kw):
            raise RuntimeError("DB password='leakyvalue' at /home/secret.py:42")

        with patch("app.cascade.orchestrator.call_with_cascade", side_effect=_raise):
            result = await mod._live_test_provider("x")

    assert result["ok"] is False
    assert result["error"] == "internal_error"
    assert "request_id" in result
    # Never echo the raw exception body to the caller
    assert "leakyvalue" not in str(result)
    assert "/home/secret.py" not in str(result)
    assert "Traceback" not in str(result)


@pytest.mark.asyncio
async def test_live_test_provider_provider_error_message_capped():
    from app.api.admin import providers_save as mod
    from app.providers.schemas import ProviderError

    async def _raise(*_a, **_kw):
        raise ProviderError(
            provider="x",
            message="line1\nline2\nstack frame leaked: " + ("x" * 500),
        )

    with patch("app.cascade.orchestrator.call_with_cascade", side_effect=_raise):
        result = await mod._live_test_provider("groq")
    # Only first line, max 120 chars
    assert "\n" not in result["error"]
    assert len(result["error"]) <= 120


# ---------- update._safe_error_label (#12/#13) -----------------------------


def test_safe_error_label_passes_allowlisted_codes():
    from app.api.update import _safe_error_label

    assert _safe_error_label("manifest_fetch_failed") == "manifest_fetch_failed"
    assert _safe_error_label("update_manifest_url tanimli degil") == "update_manifest_url tanimli degil"


def test_safe_error_label_collapses_unknown():
    from app.api.update import _safe_error_label

    # Old-style raw exception strings get scrubbed
    assert _safe_error_label("ConnectionError: [Errno 110] timed out at httpx.py:42") == "upstream_unavailable"
    assert _safe_error_label(None) == "upstream_unavailable"
    assert _safe_error_label("") == "upstream_unavailable"


def test_safe_error_label_handles_http_status_code():
    from app.api.update import _safe_error_label

    assert _safe_error_label("manifest fetch 502") == "upstream_http_error"
    assert _safe_error_label("manifest fetch 404") == "upstream_http_error"


# ---------- end-to-end: /v1/update/changelog never echoes raw exc ---------


@pytest.mark.asyncio
async def test_changelog_error_branch_returns_safe_label():
    from app.api import update as update_mod

    async def _bad_manifest():
        # Simulates the manifest.py fix: error is the opaque code now
        return {"error": "manifest_fetch_failed", "request_id": "deadbeefcafe"}

    with patch.object(update_mod, "fetch_manifest", _bad_manifest):
        result = await update_mod.changelog(_admin={"sub": "test"})

    assert result["note"] == "manifest_fetch_failed"
    # Even if a future regression brings raw exception text, the label fn collapses it.


@pytest.mark.asyncio
async def test_changelog_error_branch_collapses_legacy_raw_exception():
    from app.api import update as update_mod

    async def _legacy_manifest():
        # Pre-fix payload (what /v1/update/changelog used to echo)
        return {"error": "ConnectionError: [Errno 110] at httpx.py:42 stack frame X"}

    with patch.object(update_mod, "fetch_manifest", _legacy_manifest):
        result = await update_mod.changelog(_admin={"sub": "test"})

    note = result["note"]
    assert "ConnectionError" not in note
    assert "httpx.py" not in note
    assert "stack frame" not in note
    assert note == "upstream_unavailable"
