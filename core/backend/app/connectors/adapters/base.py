# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Connector adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class CredentialField:
    """A field the UI renders to collect this connector's credentials."""

    key: str
    label: str
    type: str = "text"           # text | password | textarea | file
    placeholder: str = ""
    required: bool = True


@dataclass
class SyncResult:
    companies: int = 0
    contacts: int = 0
    leads: int = 0
    error: str = ""

    @property
    def total(self) -> int:
        return self.companies + self.contacts + self.leads

    def to_dict(self) -> dict:
        return {
            "companies": self.companies, "contacts": self.contacts,
            "leads": self.leads, "total": self.total, "error": self.error,
        }


class ConnectorAdapter(ABC):
    """Base class for a real connector integration.

    ``auth_kind``: none | api_key | oauth | file. ``credential_fields`` drives
    the panel's connect form. ``test_connection`` validates creds without
    side-effects; ``sync`` pulls records into the growth tables.
    """

    connector_id: str = ""
    auth_kind: str = "none"
    credential_fields: List[CredentialField] = field(default_factory=list)  # type: ignore[assignment]

    @abstractmethod
    async def test_connection(self, creds: dict) -> tuple[bool, str]:
        """Return (ok, message). Must NOT mutate any tenant data."""

    @abstractmethod
    async def sync(self, tenant_slug: str, creds: dict) -> SyncResult:
        """Pull records into companies/contacts/leads. Returns counts."""
