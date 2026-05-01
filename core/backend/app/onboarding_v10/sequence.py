"""T-047 — Onboarding email sequence (welcome / walkthrough / first_success / expiry)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

__all__ = [
    "EmailKind",
    "OnboardingPlan",
    "OnboardingScheduler",
    "build_onboarding_plan",
]


EmailKind = str  # "welcome" | "walkthrough" | "first_success" | "expiry_warning"


@dataclass(slots=True)
class OnboardingPlan:
    license_jti: str
    customer_email: str
    tenant_id: str
    locale: str
    schedule: list[tuple[EmailKind, str]] = field(default_factory=list)


_DEFAULT_OFFSETS_HOURS = {
    "welcome": 0,
    "walkthrough": 24,
    "first_success": 72,
    "expiry_warning": 24 * 23,
}


def build_onboarding_plan(
    *,
    license_jti: str,
    customer_email: str,
    tenant_id: str,
    locale: str = "en",
    issued_at: datetime | None = None,
    offsets_hours: dict[EmailKind, int] | None = None,
) -> OnboardingPlan:
    if not license_jti or not customer_email or not tenant_id:
        raise ValueError("license_jti, customer_email and tenant_id required")
    base = issued_at or datetime.now(timezone.utc)
    offsets = offsets_hours or _DEFAULT_OFFSETS_HOURS
    schedule = sorted(
        (
            (kind, (base + timedelta(hours=hours)).isoformat(timespec="seconds"))
            for kind, hours in offsets.items()
        ),
        key=lambda x: x[1],
    )
    return OnboardingPlan(
        license_jti=license_jti,
        customer_email=customer_email,
        tenant_id=tenant_id,
        locale=locale,
        schedule=schedule,
    )


class OnboardingScheduler:
    """Tracks per-license sent state with idempotent send hooks."""

    def __init__(self) -> None:
        self._plans: dict[str, OnboardingPlan] = {}
        self._sent: dict[str, set[EmailKind]] = {}

    def register(self, plan: OnboardingPlan) -> None:
        if plan.license_jti in self._plans:
            raise ValueError(f"plan {plan.license_jti!r} already registered")
        self._plans[plan.license_jti] = plan
        self._sent[plan.license_jti] = set()

    def due(self, *, now: datetime | None = None) -> list[tuple[str, EmailKind]]:
        clock = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        out: list[tuple[str, EmailKind]] = []
        for plan in self._plans.values():
            sent = self._sent[plan.license_jti]
            for kind, when in plan.schedule:
                if kind in sent:
                    continue
                if when <= clock:
                    out.append((plan.license_jti, kind))
        return out

    def mark_sent(self, *, license_jti: str, kind: EmailKind) -> bool:
        sent = self._sent.get(license_jti)
        if sent is None:
            raise KeyError(f"plan {license_jti!r} not registered")
        if kind in sent:
            return False
        sent.add(kind)
        logger.info(
            "onboarding_sent jti=%s kind=%s remaining=%d",
            license_jti,
            kind,
            len(self._plans[license_jti].schedule) - len(sent),
        )
        return True

    def cancel(self, *, license_jti: str) -> bool:
        if license_jti not in self._plans:
            return False
        del self._plans[license_jti]
        del self._sent[license_jti]
        return True
