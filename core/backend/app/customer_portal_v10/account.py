"""T-041 — Customer portal account + project store (tenant-scoped, in-memory)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = [
    "Account",
    "AccountStore",
    "Invite",
    "Project",
    "PortalProjects",
]


@dataclass(slots=True)
class Account:
    account_id: str
    tenant_id: str
    email: str
    name: str
    role: str = "member"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Invite:
    invite_id: str
    tenant_id: str
    email: str
    role: str
    invited_by: str


@dataclass(slots=True)
class Project:
    project_id: str
    tenant_id: str
    name: str
    owner_email: str
    archived: bool = False


class AccountStore:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._invites: dict[str, Invite] = {}

    def add(self, account: Account) -> Account:
        if not account.tenant_id:
            raise ValueError("tenant_id required")
        self._accounts[account.account_id] = account
        return account

    def for_tenant(self, tenant_id: str) -> list[Account]:
        return [a for a in self._accounts.values() if a.tenant_id == tenant_id]

    def invite(
        self,
        *,
        tenant_id: str,
        email: str,
        role: str,
        invited_by_role: str,
    ) -> Invite:
        if invited_by_role not in {"admin", "owner"}:
            raise PermissionError("only admin/owner can invite")
        if not tenant_id or not email:
            raise ValueError("tenant_id and email required")
        invite = Invite(
            invite_id=uuid.uuid4().hex[:12],
            tenant_id=tenant_id,
            email=email,
            role=role,
            invited_by=invited_by_role,
        )
        self._invites[invite.invite_id] = invite
        logger.info(
            "invite_created tenant=%s email=%s role=%s", tenant_id, email, role
        )
        return invite

    def revoke(self, invite_id: str) -> bool:
        return self._invites.pop(invite_id, None) is not None

    def pending_invites(self, tenant_id: str) -> list[Invite]:
        return [i for i in self._invites.values() if i.tenant_id == tenant_id]


class PortalProjects:
    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}

    def create(
        self,
        *,
        tenant_id: str,
        name: str,
        owner_email: str,
    ) -> Project:
        if not tenant_id or not name or not owner_email:
            raise ValueError("tenant_id, name, and owner_email required")
        project = Project(
            project_id=uuid.uuid4().hex[:12],
            tenant_id=tenant_id,
            name=name,
            owner_email=owner_email,
        )
        self._projects[project.project_id] = project
        return project

    def archive(self, *, project_id: str, tenant_id: str) -> bool:
        project = self._projects.get(project_id)
        if project is None or project.tenant_id != tenant_id:
            return False
        project.archived = True
        return True

    def for_tenant(self, tenant_id: str, *, include_archived: bool = False) -> list[Project]:
        return [
            p
            for p in self._projects.values()
            if p.tenant_id == tenant_id and (include_archived or not p.archived)
        ]

    def get(self, *, project_id: str, tenant_id: str) -> Project | None:
        project = self._projects.get(project_id)
        if project is None or project.tenant_id != tenant_id:
            return None
        return project
