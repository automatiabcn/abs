# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Voice fingerprint → user_id mapping (consent + GDPR-compliant).

Mock backend stores SHA-256 of an arbitrary fingerprint blob. Real backend
will plug in pyannote speaker embeddings; identical interface keeps the
swap zero-cost. ConsentRequired error is raised when
`settings.meeting_voice_consent_required=True` and no consent record exists.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "ConsentRequired",
    "SpeakerProfile",
    "SpeakerRegistry",
]


class ConsentRequired(RuntimeError):
    """Raised when enrolment is attempted without explicit consent."""


@dataclass(slots=True)
class SpeakerProfile:
    user_id: str
    tenant_id: str
    fingerprint_hash: str
    consent_at: str  # ISO timestamp
    metadata: dict[str, str]


class SpeakerRegistry:
    """In-memory registry; production swaps to a tenant-scoped DB table."""

    def __init__(self) -> None:
        self._profiles: dict[str, SpeakerProfile] = {}

    @staticmethod
    def _hash(fingerprint: bytes | str) -> str:
        if isinstance(fingerprint, str):
            fingerprint = fingerprint.encode("utf-8")
        return hashlib.sha256(fingerprint).hexdigest()

    def enroll(
        self,
        *,
        user_id: str,
        tenant_id: str,
        fingerprint: bytes | str,
        consent_at: str,
        metadata: dict[str, str] | None = None,
    ) -> SpeakerProfile:
        if getattr(settings, "meeting_voice_consent_required", True) and not consent_at:
            raise ConsentRequired("explicit consent_at timestamp required")
        digest = self._hash(fingerprint)
        profile = SpeakerProfile(
            user_id=user_id,
            tenant_id=tenant_id,
            fingerprint_hash=digest,
            consent_at=consent_at,
            metadata=dict(metadata or {}),
        )
        self._profiles[digest] = profile
        logger.info(
            "speaker_enroll user=%s tenant=%s digest=%s",
            user_id,
            tenant_id,
            digest[:12],
        )
        return profile

    def identify(
        self, fingerprint: bytes | str, *, tenant_id: str
    ) -> SpeakerProfile | None:
        digest = self._hash(fingerprint)
        profile = self._profiles.get(digest)
        if profile is None or profile.tenant_id != tenant_id:
            return None
        return profile

    def forget(self, *, user_id: str) -> int:
        """GDPR Article 17 — purge a user's profile(s); returns count removed."""
        to_remove = [d for d, p in self._profiles.items() if p.user_id == user_id]
        for d in to_remove:
            del self._profiles[d]
        if to_remove:
            logger.info("speaker_forget user=%s removed=%d", user_id, len(to_remove))
        return len(to_remove)
