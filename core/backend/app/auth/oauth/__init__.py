"""T-003 — OAuth 2.1 authorization server (Authorization Code + PKCE).

Public surface:
    issue_authorization_code, exchange_code_for_tokens, refresh_access_token,
    verify_access_token, jwks
Routes are exported via app.auth.oauth.routes.router (mounted in main.py).
"""

from app.auth.oauth.jwks import current_kid, jwks_document
from app.auth.oauth.server import (
    exchange_code_for_tokens,
    issue_authorization_code,
    refresh_access_token,
    verify_access_token,
)

__all__ = [
    "current_kid",
    "exchange_code_for_tokens",
    "issue_authorization_code",
    "jwks_document",
    "refresh_access_token",
    "verify_access_token",
]
