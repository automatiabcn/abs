# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-035 — Gmail MCP server (read/draft/send/label) with per-tenant token vault.

Mock backend simulates the Gmail API; real backend gated behind
`google-api-python-client` deferred import. OAuth 2.0 PKCE token storage
is plain-dict here; production wires it into the existing
`app.vault.cache` SOPS-encrypted store (T-027 vault).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = [
    "GmailMessage",
    "GmailQuotaExceeded",
    "GmailTokenVault",
    "GmailMCP",
]


class GmailQuotaExceeded(RuntimeError):
    """Raised when the per-tenant rate limit (250 quota units / second) is breached."""


@dataclass(slots=True)
class GmailMessage:
    message_id: str
    thread_id: str
    sender: str
    recipients: list[str]
    subject: str
    snippet: str
    body: str
    labels: list[str] = field(default_factory=list)
    received_at: float = 0.0


class GmailTokenVault:
    """Per-tenant OAuth refresh-token store. Production wraps `app.vault.cache`."""

    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, str]] = {}

    def store(self, *, tenant_id: str, refresh_token: str, scope: str) -> None:
        if not tenant_id or not refresh_token:
            raise ValueError("tenant_id and refresh_token required")
        self._tokens[tenant_id] = {
            "refresh_token": refresh_token,
            "scope": scope,
            "stored_at": str(time.time()),
        }
        logger.info("gmail_token_store tenant=%s scope=%s", tenant_id, scope)

    def get(self, tenant_id: str) -> dict[str, str]:
        token = self._tokens.get(tenant_id)
        if token is None:
            raise KeyError(f"no Gmail token for tenant {tenant_id!r}")
        return token

    def revoke(self, tenant_id: str) -> bool:
        return self._tokens.pop(tenant_id, None) is not None


class _MockBackend:
    def __init__(self) -> None:
        self._messages: dict[str, list[GmailMessage]] = {}

    def list(self, tenant_id: str, *, limit: int = 50) -> list[GmailMessage]:
        return list(self._messages.get(tenant_id, []))[-limit:]

    def get(self, tenant_id: str, message_id: str) -> GmailMessage:
        for m in self._messages.get(tenant_id, []):
            if m.message_id == message_id:
                return m
        raise KeyError(f"message_id {message_id!r} not found")

    def insert_for_test(
        self,
        tenant_id: str,
        *,
        sender: str,
        subject: str,
        body: str,
    ) -> GmailMessage:
        msg = GmailMessage(
            message_id=uuid.uuid4().hex[:12],
            thread_id=uuid.uuid4().hex[:8],
            sender=sender,
            recipients=["inbox@abs.local"],
            subject=subject,
            snippet=body[:80],
            body=body,
            received_at=time.time(),
        )
        self._messages.setdefault(tenant_id, []).append(msg)
        return msg

    def draft(
        self, tenant_id: str, *, thread_id: str, subject: str, body: str
    ) -> str:
        draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        logger.info(
            "gmail_draft tenant=%s thread=%s draft=%s subject_len=%d",
            tenant_id,
            thread_id,
            draft_id,
            len(subject),
        )
        return draft_id

    def send(self, tenant_id: str, *, draft_id: str) -> str:
        msg_id = f"sent-{uuid.uuid4().hex[:12]}"
        logger.info("gmail_send tenant=%s draft=%s msg=%s", tenant_id, draft_id, msg_id)
        return msg_id

    def label(
        self, tenant_id: str, *, message_id: str, add: list[str], remove: list[str]
    ) -> None:
        for m in self._messages.get(tenant_id, []):
            if m.message_id == message_id:
                for a in add:
                    if a not in m.labels:
                        m.labels.append(a)
                m.labels = [l for l in m.labels if l not in remove]
                return


class _GoogleBackend:
    """T-Q03 — real Gmail REST client.

    Uses the Gmail v1 REST endpoints directly via httpx instead of the
    `google-api-python-client` SDK so we avoid pulling a 30 MB dependency
    chain in. The token vault refreshes the OAuth access token on demand.

    Endpoints:
      GET  /gmail/v1/users/me/messages?q=in:inbox&maxResults=N
      GET  /gmail/v1/users/me/messages/<id>
      POST /gmail/v1/users/me/drafts
      POST /gmail/v1/users/me/drafts/<id>/send
      POST /gmail/v1/users/me/messages/<id>/modify
    """

    BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, vault: "GmailTokenVault") -> None:
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise ImportError("google backend requires httpx") from exc
        self.vault = vault
        self._access_tokens: dict[str, tuple[str, float]] = {}

    def _access_token(self, tenant_id: str) -> str:
        cached = self._access_tokens.get(tenant_id)
        if cached and cached[1] > time.time() + 30:
            return cached[0]
        import httpx

        from app.config import settings as _s

        record = self.vault.get(tenant_id)
        client_id = getattr(_s, "gmail_oauth_client_id", "") or ""
        client_secret = getattr(_s, "gmail_oauth_client_secret", "") or ""
        if not (client_id and client_secret):
            raise RuntimeError(
                "Gmail OAuth client credentials missing (ABS_GMAIL_OAUTH_CLIENT_ID / SECRET)"
            )
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                self.OAUTH_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": record["refresh_token"],
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            data = r.json()
        token = str(data["access_token"])
        expires_at = time.time() + float(data.get("expires_in", 3600))
        self._access_tokens[tenant_id] = (token, expires_at)
        return token

    def _headers(self, tenant_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token(tenant_id)}",
            "Accept": "application/json",
        }

    def list(self, tenant_id: str, *, limit: int = 50) -> list[GmailMessage]:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{self.BASE_URL}/messages",
                params={"q": "in:inbox", "maxResults": limit},
                headers=self._headers(tenant_id),
            )
            r.raise_for_status()
            ids = [m["id"] for m in r.json().get("messages", [])]
            results: list[GmailMessage] = []
            for mid in ids:
                rd = client.get(
                    f"{self.BASE_URL}/messages/{mid}",
                    params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject"]},
                    headers=self._headers(tenant_id),
                )
                rd.raise_for_status()
                msg = rd.json()
                hdr = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                results.append(
                    GmailMessage(
                        message_id=str(msg.get("id")),
                        thread_id=str(msg.get("threadId", "")),
                        sender=hdr.get("From", ""),
                        recipients=[hdr.get("To", "")] if hdr.get("To") else [],
                        subject=hdr.get("Subject", ""),
                        snippet=str(msg.get("snippet", ""))[:200],
                        body="",
                        labels=list(msg.get("labelIds", [])),
                        received_at=float(msg.get("internalDate", 0)) / 1000.0,
                    )
                )
        return results

    def draft(
        self, tenant_id: str, *, thread_id: str, subject: str, body: str
    ) -> str:
        import base64
        import httpx

        raw = (
            f"To: \r\nSubject: {subject}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}"
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("ascii")
        payload = {"message": {"threadId": thread_id, "raw": encoded}}
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.BASE_URL}/drafts",
                json=payload,
                headers={**self._headers(tenant_id), "Content-Type": "application/json"},
            )
            r.raise_for_status()
            return str(r.json()["id"])

    def send(self, tenant_id: str, *, draft_id: str) -> str:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.BASE_URL}/drafts/send",
                json={"id": draft_id},
                headers={**self._headers(tenant_id), "Content-Type": "application/json"},
            )
            r.raise_for_status()
            return str(r.json()["id"])

    def label(
        self, tenant_id: str, *, message_id: str, add: list[str], remove: list[str]
    ) -> None:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{self.BASE_URL}/messages/{message_id}/modify",
                json={"addLabelIds": add, "removeLabelIds": remove},
                headers={**self._headers(tenant_id), "Content-Type": "application/json"},
            )
            r.raise_for_status()


class GmailMCP:
    backend: str

    def __init__(self, *, backend: str = "mock", vault: GmailTokenVault | None = None) -> None:
        self.backend = backend
        self.vault = vault or GmailTokenVault()
        if backend == "mock":
            self._impl: object = _MockBackend()
        elif backend == "google":
            self._impl = _GoogleBackend(self.vault)
        else:
            raise ValueError(f"unsupported gmail backend: {backend}")
        self._rate_buckets: dict[str, tuple[float, int]] = {}

    def _rate_check(self, tenant_id: str, *, units: int) -> None:
        now = time.time()
        window_start, used = self._rate_buckets.get(tenant_id, (now, 0))
        if now - window_start >= 1.0:
            window_start = now
            used = 0
        if used + units > 250:
            raise GmailQuotaExceeded(
                f"tenant {tenant_id!r} exceeded 250 quota units/second"
            )
        self._rate_buckets[tenant_id] = (window_start, used + units)

    def list_inbox(self, *, tenant_id: str, limit: int = 50) -> list[GmailMessage]:
        self._rate_check(tenant_id, units=5)
        return self._impl.list(tenant_id, limit=limit)  # type: ignore[attr-defined]

    def draft_reply(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        subject: str,
        body: str,
    ) -> str:
        self._rate_check(tenant_id, units=10)
        return self._impl.draft(  # type: ignore[attr-defined]
            tenant_id, thread_id=thread_id, subject=subject, body=body
        )

    def send(self, *, tenant_id: str, draft_id: str) -> str:
        self._rate_check(tenant_id, units=100)
        return self._impl.send(tenant_id, draft_id=draft_id)  # type: ignore[attr-defined]

    def label(
        self,
        *,
        tenant_id: str,
        message_id: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        self._rate_check(tenant_id, units=5)
        self._impl.label(  # type: ignore[attr-defined]
            tenant_id, message_id=message_id, add=add or [], remove=remove or []
        )
