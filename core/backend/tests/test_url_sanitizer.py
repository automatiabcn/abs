# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2E ITEM-A — URL log sanitizer unit tests.

Defence-in-depth alongside Gemini header-auth migration: any future HTTP
client that logs a URL with `?key=` / `?token=` / etc. must have the
secret redacted before reaching stdout.
"""

from __future__ import annotations

import logging

from app.observability.url_sanitizer import (
    SecretQueryParamFilter,
    install_url_log_sanitizer,
    sanitize_url_for_log,
)


# ─── sanitize_url_for_log ───────────────────────────────────────────────


def test_sanitize_redacts_key_param() -> None:
    out = sanitize_url_for_log("https://x.example/y?key=AIzaSyDXXX")
    assert out == "https://x.example/y?key=REDACTED"
    assert "AIzaSyDXXX" not in out


def test_sanitize_redacts_token_param_preserving_others() -> None:
    out = sanitize_url_for_log("https://x.example/y?token=abc123&other=keep")
    assert out == "https://x.example/y?token=REDACTED&other=keep"
    assert "keep" in out
    assert "abc123" not in out


def test_sanitize_redacts_api_key_variants() -> None:
    for raw, expected_secret in [
        ("https://x/y?api_key=SECRET_A", "SECRET_A"),
        ("https://x/y?api-key=SECRET_B", "SECRET_B"),
        ("https://x/y?access_token=SECRET_C", "SECRET_C"),
        ("https://x/y?access-token=SECRET_D", "SECRET_D"),
        ("https://x/y?refresh_token=SECRET_E", "SECRET_E"),
        ("https://x/y?secret=SECRET_F", "SECRET_F"),
        ("https://x/y?auth=SECRET_G", "SECRET_G"),
        ("https://x/y?password=SECRET_H", "SECRET_H"),
        ("https://x/y?client_secret=SECRET_I", "SECRET_I"),
    ]:
        out = sanitize_url_for_log(raw)
        assert expected_secret not in out, f"leaked: {raw}"
        assert "REDACTED" in out


def test_sanitize_redacts_multiple_secrets_in_same_url() -> None:
    out = sanitize_url_for_log("https://x/y?key=AAA&token=BBB&visible=ok&secret=CCC")
    assert "AAA" not in out
    assert "BBB" not in out
    assert "CCC" not in out
    assert "visible=ok" in out
    assert out.count("REDACTED") == 3


def test_sanitize_is_case_insensitive_on_param_name() -> None:
    out = sanitize_url_for_log("https://x/y?KEY=SECRET&Token=OTHER")
    assert "SECRET" not in out
    assert "OTHER" not in out


def test_sanitize_passes_through_url_without_secrets() -> None:
    url = "https://x.example/y?id=42&page=1"
    assert sanitize_url_for_log(url) == url


def test_sanitize_handles_empty_or_none_safely() -> None:
    assert sanitize_url_for_log("") == ""
    assert sanitize_url_for_log("https://x/no-query") == "https://x/no-query"


def test_sanitize_only_matches_query_param_form() -> None:
    # "key" appearing inside a path segment shouldn't be touched.
    out = sanitize_url_for_log("https://x.example/keystore/abc")
    assert out == "https://x.example/keystore/abc"


# ─── SecretQueryParamFilter ─────────────────────────────────────────────


def test_filter_redacts_msg_string() -> None:
    flt = SecretQueryParamFilter()
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="GET https://x/y?key=LEAKED",
        args=None,
        exc_info=None,
    )
    flt.filter(rec)
    assert "LEAKED" not in rec.getMessage()
    assert "REDACTED" in rec.getMessage()


def test_filter_redacts_tuple_args() -> None:
    flt = SecretQueryParamFilter()
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="%s %s",
        args=("GET", "https://x/y?token=LEAKED_T"),
        exc_info=None,
    )
    flt.filter(rec)
    assert "LEAKED_T" not in rec.getMessage()


# ─── install_url_log_sanitizer ──────────────────────────────────────────


def test_install_is_idempotent() -> None:
    install_url_log_sanitizer()
    install_url_log_sanitizer()  # second call must not duplicate
    httpx_logger = logging.getLogger("httpx")
    matches = [f for f in httpx_logger.filters if isinstance(f, SecretQueryParamFilter)]
    assert len(matches) == 1
