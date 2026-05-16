# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q12 IP-Hardening R3 — image-only customer distribution tests.

Coverage (5 tests):
    1. infra/docker-compose.customer.yml uses `image:` only — no `build:`.
    2. scripts/release.sh refuses to build with a dirty working tree
       (clean-tree gate is the contract that BUILD_HASH stays trustworthy).
    3. Backend Dockerfile production stage strips license-critical .py
       source when ABS_COMPILE_CYTHON=1.
    4. Backend Dockerfile carries the abs.build.hash OCI label so the
       activation server can verify the image at phone-home time.
    5. Customer onboarding email no longer mentions `git clone` and does
       reference the ghcr.io image-pull workflow.
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_customer_compose_no_build_context():
    compose = yaml.safe_load(_read("infra/docker-compose.customer.yml"))
    services = compose.get("services") or {}
    assert services, "customer compose missing services block"

    for name, svc in services.items():
        # caddy is upstream image; backend/landing/email-cron must use
        # ghcr.io images. Either way: NO `build:` key allowed.
        assert "build" not in svc, (
            f"service {name!r} must use image-only distribution, "
            f"found build context: {svc.get('build')!r}"
        )

    # Sprint 2N.2 FAZ B: customer compose now parameterizes the GHCR
    # namespace (ABS_GHCR_NAMESPACE) so the publishing workflow (which
    # holds `automatiabcn` org scope) and operators pinned to the
    # pre-2N.2 `enzoemir1` namespace can both pull. Accept the templated
    # form or either literal as long as the image base is right.
    for app in ("backend", "landing"):
        image = services[app].get("image", "")
        assert image.startswith("ghcr.io/") and f"/abs-{app}:" in image, (
            f"{app} must pull from ghcr.io/.../abs-{app}:*, got {image!r}"
        )


def test_release_script_atomic_clean_tree_gate():
    text = _read("scripts/release.sh")
    assert "set -euo pipefail" in text
    assert "git status --porcelain" in text, "release.sh must check working tree"
    assert "working tree dirty" in text, "release.sh must explicitly refuse dirty trees"
    # Build hash must blend git + source so a tampered image is detectable.
    assert "BUILD_HASH" in text
    assert "ABS_COMPILE_CYTHON=1" in text, (
        "release.sh must enable Cython for production builds"
    )
    # Image refs may interpolate ${GHCR_USER} — accept either literal or
    # template form so long as the registry + repo are unambiguous.
    # Sprint 2N.2 FAZ B: default GHCR_USER switched from enzoemir1 to
    # automatiabcn so the publishing workflow's GITHUB_TOKEN can push.
    backend_present = (
        "ghcr.io/automatiabcn/abs-backend" in text
        or "ghcr.io/enzoemir1/abs-backend" in text
        or "ghcr.io/${GHCR_USER}/abs-backend" in text
    )
    landing_present = (
        "ghcr.io/automatiabcn/abs-landing" in text
        or "ghcr.io/enzoemir1/abs-landing" in text
        or "ghcr.io/${GHCR_USER}/abs-landing" in text
    )
    assert backend_present, "release.sh must build the abs-backend ghcr image"
    assert landing_present, "release.sh must build the abs-landing ghcr image"
    assert "automatiabcn" in text or "enzoemir1" in text, (
        "release.sh must reference a known GHCR namespace"
    )


def test_dockerfile_strips_license_source():
    text = _read("core/backend/Dockerfile")
    # When Cython compile is on, the source .py for verifier / fingerprint
    # / quota_monitor must be deleted so only the .so survives.
    for module in (
        "app/licensing/verifier.py",
        "app/licensing/fingerprint.py",
        "app/observability/quota_monitor.py",
    ):
        assert module in text, f"Dockerfile no longer references {module}"
    assert "rm -f app/licensing/verifier.py" in text
    # Runtime stage must copy app/ from the post-Cython builder, NOT from
    # the host build context — that's what enforces the source strip.
    assert "COPY --from=builder /app/app /app/app" in text


def test_dockerfile_carries_build_hash_label():
    text = _read("core/backend/Dockerfile")
    assert "ARG BUILD_HASH" in text
    assert "ENV ABS_BUILD_HASH=${BUILD_HASH}" in text
    assert 'LABEL abs.build.hash="${BUILD_HASH}"' in text or \
           'abs.build.hash="${BUILD_HASH}"' in text, (
        "Dockerfile must apply the abs.build.hash OCI label so the "
        "activation server can verify the image at phone-home time"
    )


def test_customer_onboard_email_uses_ghcr_pull():
    text = _read("scripts/customer_onboard.sh")
    # Old SSH+git-clone flow must be gone.
    assert "git@github.com:enzoemir1/abs.git" not in text, (
        "Customer onboarding still references the source-clone path"
    )
    assert "GIT_SSH_COMMAND" not in text
    # New ghcr.io flow must be present.
    assert "ghcr.io" in text
    assert "ghcr_pull.token" in text
    assert "docker login ghcr.io" in text
    assert "docker compose pull" in text
    # Customer compose must be shipped to the customer.
    assert "infra/docker-compose.customer.yml" in text
