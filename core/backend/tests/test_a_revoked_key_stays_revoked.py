# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A revoked access key came back to life if you changed one character of it.

The token is `abs_mcp_<body>.<signature>`, both base64url. Thirty-two signature
bytes are 256 bits; the 43 characters that carry them hold 258. The last
character has two bits nobody reads — so `…A` and `…B` decode to the same
signature, and both pass the HMAC check, because by every measure the signature
can see they *are* the same key.

Revocation did not use that measure. It hashed the token string, so the
blacklist row it wrote was for one spelling of the key, and the other spellings
walked straight past it: HMAC valid, digest unknown, welcome in.

Which means the operator whose key leaked, who did the one thing the product
tells them to do, still had an attacker on the server — holding a key they had
watched turn red in the panel, and needing to retype a single character of it.

The keys are handed to Claude Code, editors, scripts on laptops. They leak. The
revoke button is the entire security story of that surface, and it had a hole
one keystroke wide.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.mcp_tokens import _sign, verify_token


def _token(**over) -> str:
    import time

    payload = {
        "tenant": "default",
        "scope": "mcp",
        "label": "test",
        "exp": int(time.time()) + 3600,
        **over,
    }
    return _sign(payload)


def test_the_key_it_was_minted_as_still_works() -> None:
    payload = verify_token(_token())
    assert payload["scope"] == "mcp"


@pytest.mark.parametrize("swap", ["A", "B", "C", "_", "-"])
def test_one_character_of_the_signature_is_a_different_key_and_is_refused(
    swap: str,
) -> None:
    token = _token()
    if token.endswith(swap):
        pytest.skip("that is the token itself, not a variant of it")

    with pytest.raises(HTTPException) as caught:
        verify_token(token[:-1] + swap)
    assert caught.value.status_code == 401


def test_a_revoked_key_cannot_be_retyped_back_to_life(monkeypatch) -> None:
    """The damage, stated as the attacker would state it.

    Not "does verify_token return 401" — that is the mechanism. This is the
    consequence: a key on the blacklist must not authenticate under any spelling.
    """
    token = _token(label="leaked")
    assert verify_token(token)["label"] == "leaked"

    revoked: set[str] = set()
    monkeypatch.setattr(
        "app.api.mcp_tokens._is_revoked", lambda t: t in revoked, raising=True
    )
    revoked.add(token)

    with pytest.raises(HTTPException):
        verify_token(token)

    # The attacker still holds the key. They change the last character — the one
    # the signature cannot see — and try again.
    variant = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(HTTPException) as caught:
        verify_token(variant)
    assert caught.value.status_code == 401, (
        "a key the operator revoked authenticated again after one character was changed"
    )
