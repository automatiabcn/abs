# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Regression locks for the 2026-06-05 live-ops session.

Each test pins a fix made while bringing a self-host customer up, so the incident cannot
silently recur:
  * RAG file ingest: /v1/rag/ingest-file body cap (40 MB) + longest-prefix wins
    over /v1/rag/ingest (10 MB).
  * Parser: unsupported binary mime is handled, not a 500.
  * Cloudflare: runtime name maps to the registry name "cloudflare"
    (was "cloudflare_workers_ai" → unknown → bad creds silently accepted).
"""

from __future__ import annotations

import pytest

from app.middleware.body_size_limit import BodySizeLimitMiddleware, DEFAULT_CAPS


# ---------- body-size caps ----------


def test_ingest_file_cap_is_40mb_and_beats_ingest_prefix() -> None:
    mw = BodySizeLimitMiddleware(None, caps=DEFAULT_CAPS)
    # longest-prefix: /v1/rag/ingest-file must resolve to its own 40 MB cap,
    # NOT the shorter /v1/rag/ingest 10 MB prefix.
    assert mw._cap_for("/v1/rag/ingest-file") == 40 * 1024 * 1024
    assert mw._cap_for("/v1/rag/ingest") == 10 * 1024 * 1024


def test_ingest_file_cap_under_hardcap() -> None:
    # 40 MB raw-upload cap must stay below the absolute 50 MB hardcap.
    assert DEFAULT_CAPS["/v1/rag/ingest-file"] <= DEFAULT_CAPS["_hardcap"]


# ---------- parser: unsupported mime is graceful ----------


def test_parse_document_unknown_binary_mime_falls_back_to_text() -> None:
    from app.rag import pipeline_v10 as pipe

    # An unknown mime is treated as text (not routed to PDF/DOCX parser),
    # so arbitrary uploads never 500 the ingest path.
    doc = pipe.parse_document(
        b"plain bytes", mime_type="application/x-zip", filename="z.bin"
    )
    assert doc.text == "plain bytes"


def test_extract_binary_text_rejects_unknown_mime_cleanly() -> None:
    from app.rag import pipeline_v10 as pipe

    # If the binary-parser path is reached with a mime it can't handle, it
    # raises a clean RuntimeError (which the route maps to 422), never a
    # raw library exception (→ 500).
    with pytest.raises(RuntimeError) as exc:
        pipe._extract_binary_text(b"\x00\x01", "application/x-unknown-binary")
    assert "no_parser_for_mime" in str(exc.value)


# ---------- cloudflare runtime name ----------


def test_cloudflare_runtime_name_matches_registry() -> None:
    from app.api.admin import providers_save, providers_status

    # Both the save-test and the status-test must use the registry name
    # "cloudflare" — "cloudflare_workers_ai" was unknown to the registry,
    # so the live test 503'd and bad Cloudflare creds were silently accepted.
    assert providers_save._PROVIDER_RUNTIME_NAME["cloudflare"] == "cloudflare"
    assert providers_status._PROVIDER_RUNTIME_NAME["cloudflare"] == "cloudflare"


def test_cloudflare_provider_registered_under_cloudflare() -> None:
    from app.providers.registry import get_provider

    prov = get_provider("cloudflare")
    assert prov is not None
    assert getattr(prov, "name", None) == "cloudflare"
    # The stale name must NOT resolve.
    with pytest.raises(KeyError):
        get_provider("cloudflare_workers_ai")
