# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""What the panel showed a customer whose provider key had a typo in it:

    ✗ Cohere UnauthorizedError: headers: {'cache-control': 'no-cache, no-store,
      no-transform, must-revalidate, private, max-age=0', 'content-encoding':
      'gzip', 'conte…

The provider SDK's exception, HTTP response headers and all, truncated mid-word,
in the box where someone was trying to paste an API key. It does not say what is
wrong, it does not say what to do, and it publishes our internals to answer a
question nobody asked.

The exception still goes to the log. What reaches the customer is a sentence.
"""

from __future__ import annotations

import pytest

from app.api.admin.provider_keys import _explain


class _Unauthorized(Exception):
    pass


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_Unauthorized("UnauthorizedError: headers: {'x': 1}"), "rejected this key"),
        (TimeoutError("timed out"), "did not answer in time"),
        (Exception("429 rate limit exceeded"), "out of quota"),
        (Exception("403 Forbidden"), "refused the request"),
        (Exception("404 model not found"), "could not find"),
    ],
)
def test_the_customer_gets_a_sentence(exc: Exception, expected: str) -> None:
    reason = _explain("cohere", exc)
    assert expected in reason
    assert reason.startswith("Cohere")
    # None of the machinery leaks through.
    assert "headers" not in reason.lower()
    assert "{" not in reason


def test_an_unrecognised_failure_still_says_something_useful() -> None:
    reason = _explain("groq", Exception("\x00\x01 weird internal state"))
    assert reason == "Groq refused the key, and did not say why."
    assert "weird internal state" not in reason
