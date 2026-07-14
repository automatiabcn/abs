"""Customer package mount completeness audit.

Every host bind mount in the customer compose (`./xxx:/etc/...:ro`)
counterpart MUST exist in the customer package. The incident that taught us this:
`./cerbos` was mounted but missing from the package → cerbos container exit
→ backend couldn't talk to Cerbos PDP → half the project 503.

This test makes that pattern systematic:
- every mount starting with `./` in compose → should be in customer pkg
- `build_customer_pkg.sh` single-file tar.gz generator, mount list
  kontrol edip eksik varsa exit-1
- `customer_onboard.sh` her host bind mount'u kopyalar (cerbos + scripts +
  Caddyfile + license.jwt + ghcr_pull.token + docker-compose.yml)
"""

from __future__ import annotations

import pathlib
import re
import stat

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]

COMPOSE = REPO_ROOT / "infra" / "docker-compose.customer.yml"
ONBOARD_SH = REPO_ROOT / "scripts" / "customer_onboard.sh"
BUILDER_SH = REPO_ROOT / "scripts" / "build_customer_pkg.sh"

# customer_onboard.sh is founder-only ops tooling (.gitignored); present on the
# operator host but never in a clean checkout. Onboard-script assertions skip
# where it's absent instead of hard-failing CI.
_needs_onboard = pytest.mark.skipif(
    not ONBOARD_SH.exists(),
    reason="founder-only customer_onboard.sh (gitignored); operator host only",
)


def _host_bind_mounts() -> list[tuple[str, str]]:
    """Parse `- ./xxx:/yyy[:ro]` lines from the customer compose."""
    raw = COMPOSE.read_text()
    pattern = re.compile(r"-\s+(\./[^:]+):([^:\s]+)(?::ro)?\s*$", re.MULTILINE)
    return [(m.group(1).lstrip("./"), m.group(2)) for m in pattern.finditer(raw)]


def test_compose_has_at_least_three_host_bind_mounts() -> None:
    mounts = _host_bind_mounts()
    # Snapshot: ./scripts, ./cerbos, ./Caddyfile.
    assert len(mounts) >= 3, (
        f"compose declares {len(mounts)} host bind mount(s); expected at "
        f"least 3 (scripts, cerbos, Caddyfile). Got: {mounts}"
    )


@_needs_onboard
def test_onboard_copies_every_host_bind_mount_source() -> None:
    """For every `- ./xxx:/...` in compose, onboard.sh must materialise xxx."""
    onboard_raw = ONBOARD_SH.read_text()
    failures: list[str] = []
    for src, target in _host_bind_mounts():
        # Either `cp infra/<src>` or `cp -R infra/<src>` is acceptable;
        # also accept the bare file name when onboard ships e.g. Caddyfile
        # from infra/Caddyfile to KEYS_DIR/Caddyfile.
        clean = src.rstrip("/")
        if (
            f"infra/{clean}" not in onboard_raw
            and f"infra/{clean.lower()}" not in onboard_raw
        ):
            failures.append(
                f"compose mount './{src}' → no cp in onboard.sh (target {target})"
            )
    assert not failures, "\n".join(failures)


def test_builder_script_exists_and_executable() -> None:
    assert BUILDER_SH.exists(), "scripts/build_customer_pkg.sh missing"
    mode = BUILDER_SH.stat().st_mode
    assert mode & stat.S_IXUSR, "build_customer_pkg.sh must be chmod +x"


def test_builder_enforces_required_file_list() -> None:
    raw = BUILDER_SH.read_text()
    # Every host bind mount must appear in the REQUIRED guard array so the
    # builder fails fast if onboard.sh skipped a step.
    required_in_builder = {"docker-compose.yml", "Caddyfile", "cerbos", "scripts"}
    missing = [f for f in required_in_builder if f'"{f}"' not in raw]
    assert not missing, f"build_customer_pkg.sh REQUIRED array missing: {missing}"
    # Credentials too — license + ghcr token.
    assert '"license.jwt"' in raw
    assert '"ghcr_pull.token"' in raw


def test_builder_uses_tar_gz_single_file_pattern() -> None:
    raw = BUILDER_SH.read_text()
    assert "tar -czf" in raw, (
        "build_customer_pkg.sh must produce a tar.gz (single-file ship pattern)"
    )
    assert ".tar.gz" in raw


@_needs_onboard
def test_onboard_email_template_documents_tarball_extract() -> None:
    raw = ONBOARD_SH.read_text()
    assert "tar -xzvf" in raw, (
        "onboarding email must instruct the customer to extract the tarball "
        "(the single-file ship pattern replaces the 4-file manual "
        "placement that broke an early install)"
    )
    # The tarball name slug is interpolated into the template.
    assert "customer-pkg-" in raw


@_needs_onboard
def test_onboard_email_lists_scripts_directory() -> None:
    """The incident pattern: a scripts/ host mount never mentioned in the email."""
    raw = ONBOARD_SH.read_text()
    assert "scripts/" in raw and "email_tick" in raw, (
        "onboarding email must mention scripts/ (mounted at "
        "/app/infra/scripts) and at least one of its contents — without "
        "this the email-cron container exits immediately."
    )
