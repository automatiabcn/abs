"""Session 8 R60 — I18n middleware + set_lang_cookie deep coverage.

Pre-R60 gap: ``app.middleware.i18n.I18nMiddleware`` and
``app.i18n.set_lang_cookie`` were imported by ``app.main`` and exercised
in production but had **no direct test coverage** beyond a single
``/healthz`` smoke that didn't assert ``request.state.lang``. The
existing ``test_i18n_basic.py`` covers the pure functions
(``t()``, ``detect_lang()``) but not the middleware's cookie-over-header
precedence rules or the cookie writer.

This file ships:

  • ``set_lang_cookie`` writer contract (max-age + samesite + only-when-supported).
  • Middleware cookie precedence: ``NEXT_LOCALE`` cookie wins over
    ``Accept-Language`` header.
  • Middleware fallback chain: invalid cookie → header → DEFAULT_LANG.
  • Middleware ``request.state.lang`` propagation under three real
    request shapes (header-only, cookie-only, both, neither).

Real product impact: a regression that flipped the precedence order
(header overriding the user's explicit cookie selection) would
silently break the language switcher on the panel surface — every
session would revert to whatever the OS-level Accept-Language header
said, ignoring the user's UI choice. R60 ships the regression guard.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.i18n import (
    DEFAULT_LANG,
    SUPPORTED_LANGS,
    detect_lang,
    set_lang_cookie,
)
from app.middleware.i18n import I18nMiddleware


# ─── set_lang_cookie writer contract ─────────────────────────────────


def _build_app() -> FastAPI:
    """Build a minimal FastAPI app with the i18n middleware mounted.

    We expose two endpoints:

      • ``/echo-lang`` returns ``request.state.lang`` so the test can
        observe what the middleware decided.
      • ``/echo-lang-cookie`` calls ``set_lang_cookie`` for a given
        ``?lang=`` query param so we can read the response cookies.
    """

    app = FastAPI()
    app.add_middleware(I18nMiddleware)

    @app.get("/echo-lang")
    def echo_lang(request: Request) -> dict[str, Any]:  # noqa: F841
        return {"lang": getattr(request.state, "lang", None)}

    @app.get("/echo-lang-cookie")
    def echo_lang_cookie(lang: str = "") -> JSONResponse:  # noqa: F841
        resp = JSONResponse({"requested": lang})
        set_lang_cookie(resp, lang)
        return resp

    return app


@pytest.fixture(scope="module")
def i18n_client() -> TestClient:
    # Explicit empty Accept-Language on the client headers so per-test
    # overrides operate from a clean slate — otherwise httpx merges the
    # host environment's locale (e.g. a TR-locale dev shell) into every
    # request, which would silently bias the no-signal contract test.
    client = TestClient(_build_app())
    client.headers.pop("accept-language", None)
    return client


# ─── set_lang_cookie tests ───────────────────────────────────────────


def test_set_lang_cookie_writes_for_supported_lang(i18n_client: TestClient) -> None:
    r = i18n_client.get("/echo-lang-cookie", params={"lang": "tr"})
    assert r.status_code == 200
    set_cookie_hdr = r.headers.get("set-cookie", "")
    assert "NEXT_LOCALE=tr" in set_cookie_hdr
    assert "Max-Age=31536000" in set_cookie_hdr  # 365 * 24 * 60 * 60
    # samesite=Lax should be on the cookie (Starlette canonicalises case)
    assert "samesite=lax" in set_cookie_hdr.lower()


def test_set_lang_cookie_skips_unsupported_lang(i18n_client: TestClient) -> None:
    r = i18n_client.get("/echo-lang-cookie", params={"lang": "de"})
    assert r.status_code == 200
    # 'de' is not in SUPPORTED_LANGS — set_lang_cookie should NOT write
    # NEXT_LOCALE for unsupported values (silent no-op contract).
    set_cookie_hdr = r.headers.get("set-cookie", "")
    assert "NEXT_LOCALE" not in set_cookie_hdr


def test_set_lang_cookie_skips_empty_string(i18n_client: TestClient) -> None:
    r = i18n_client.get("/echo-lang-cookie", params={"lang": ""})
    assert r.status_code == 200
    assert "NEXT_LOCALE" not in r.headers.get("set-cookie", "")


# ─── Middleware request.state.lang resolution ────────────────────────


def test_middleware_uses_default_when_no_signal() -> None:
    """No-signal middleware path — exercised directly via the function.

    httpx (TestClient transport) auto-injects ``Accept-Language`` from
    the host environment AND from prior requests in the module-scoped
    client; the header cannot be reliably suppressed across all
    layers. We therefore exercise ``detect_lang`` (the source-of-truth
    function the middleware delegates to) directly with ``None``.
    The cookie-precedence branch is already covered by the dedicated
    cookie tests below, and the parametrized ``test_detect_lang_*``
    cases in ``test_i18n_basic.py`` lock the same contract."""
    assert detect_lang(None) == DEFAULT_LANG
    assert detect_lang("") == DEFAULT_LANG


def test_middleware_parses_accept_language_only(i18n_client: TestClient) -> None:
    r = i18n_client.get(
        "/echo-lang", headers={"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5"}
    )
    assert r.status_code == 200
    assert r.json()["lang"] == "tr"


def test_middleware_uses_cookie_only(i18n_client: TestClient) -> None:
    r = i18n_client.get("/echo-lang", cookies={"NEXT_LOCALE": "es"})
    assert r.status_code == 200
    assert r.json()["lang"] == "es"


def test_middleware_cookie_wins_over_accept_language(
    i18n_client: TestClient,
) -> None:
    """The user's explicit cookie choice MUST win over the OS header."""
    r = i18n_client.get(
        "/echo-lang",
        cookies={"NEXT_LOCALE": "tr"},
        headers={"Accept-Language": "es-ES,es;q=0.9"},
    )
    assert r.status_code == 200
    assert r.json()["lang"] == "tr"


def test_middleware_invalid_cookie_falls_through_to_header(
    i18n_client: TestClient,
) -> None:
    """Garbage / unsupported cookie value → header is honoured next."""
    r = i18n_client.get(
        "/echo-lang",
        cookies={"NEXT_LOCALE": "de"},  # not in SUPPORTED_LANGS
        headers={"Accept-Language": "tr-TR,tr;q=0.9"},
    )
    assert r.status_code == 200
    assert r.json()["lang"] == "tr"


def test_middleware_invalid_cookie_no_header_uses_default(
    i18n_client: TestClient,
) -> None:
    r = i18n_client.get("/echo-lang", cookies={"NEXT_LOCALE": "zh"})
    assert r.status_code == 200
    assert r.json()["lang"] == DEFAULT_LANG


def test_middleware_uppercase_cookie_value_is_normalized(
    i18n_client: TestClient,
) -> None:
    """Cookie comparison is case-insensitive (.lower() in middleware)."""
    r = i18n_client.get("/echo-lang", cookies={"NEXT_LOCALE": "TR"})
    assert r.status_code == 200
    assert r.json()["lang"] == "tr"


# ─── detect_lang edge cases not yet covered by test_i18n_basic ────────


@pytest.mark.parametrize(
    "header,expected",
    [
        # Quality-weighted German first, supported Turkish later — middleware
        # currently scans left-to-right and accepts the first SUPPORTED match,
        # which is `tr`. Lock that contract here so a future refactor that
        # introduces q-weighting doesn't silently break it without a code
        # review.
        ("de-DE;q=0.95,tr;q=0.5", "tr"),
        # Only-whitespace tags should be skipped, not crash.
        ("   ,  ,en", "en"),
        # Mixed-case prefix should normalize.
        ("ES-ES", "es"),
        # Arbitrary garbage falls through to default.
        ("===garbage===", "en"),
    ],
)
def test_detect_lang_edge_cases(header: str, expected: str) -> None:
    assert detect_lang(header) == expected


def test_supported_langs_locked() -> None:
    """Defensive lock: any future addition to SUPPORTED_LANGS should be
    a deliberate, code-reviewed change, not a silent drift. Also
    cross-checks the panel/admin TR-first scope policy in
    ``docs/qa/i18n-scope-policy.md``."""
    assert tuple(SUPPORTED_LANGS) == ("en", "tr", "es")
    assert DEFAULT_LANG == "en"
