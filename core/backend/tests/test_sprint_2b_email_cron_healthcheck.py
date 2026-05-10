# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Sprint 2B — email-cron healthcheck override sanity guard.

Static check: both customer + root compose files declare a process
based probe (pgrep on email_tick) and override the inherited backend
:8000 HTTP probe. The Hetzner failing-streak 58+ pre-rc7 was caused
exactly by the missing override.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _slice(text: str, anchor: str, length: int = 1200) -> str:
    idx = text.find(anchor)
    assert idx != -1, anchor
    return text[idx : idx + length]


def test_customer_compose_email_cron_has_process_healthcheck():
    compose = (
        REPO_ROOT / "infra" / "docker-compose.customer.yml"
    ).read_text(encoding="utf-8")
    cron_block = _slice(compose, "email-cron:")
    assert "healthcheck:" in cron_block
    # debian-slim backend image has no procps → no pgrep. We walk
    # /proc/[0-9]*/cmdline + grep for email_tick instead.
    assert "/proc/[0-9]*" in cron_block
    assert "email_tick" in cron_block


def test_root_compose_email_cron_has_process_healthcheck():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    cron_block = _slice(compose, "email-cron:")
    assert "healthcheck:" in cron_block
    assert "/proc/[0-9]*" in cron_block
    assert "email_tick" in cron_block
