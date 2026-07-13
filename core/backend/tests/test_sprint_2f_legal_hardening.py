"""Sprint 2F — Legal hardening artifact + CI workflow presence + content gates.

Validates ITEMs 1-8 from `_agent-tasks/WORKER_SPRINT_2F_RC11_2026-05-11.md`:

* ITEM 1: README badge + License section use BUSL-1.1 (SPDX), not "BSL".
* ITEM 2: NOTICE.md exists with copyright + BUSL-1.1 + trademark + third-party blocks.
* ITEM 3: core/landing/package.json and core/backend/pyproject.toml carry
          machine-readable `license = "BUSL-1.1"` metadata.
* ITEM 4: docs/legal/TRADEMARKS.md exists with FOSSmarks-style sections.
* ITEM 5: README License section explicitly discloses source-available / NOT OSI.
* ITEM 6: .github/workflows/sbom.yml runs cyclonedx for npm + pip with artifact upload.
* ITEM 7: .github/workflows/license-check.yml enforces licensee >=90% confidence gate.
* ITEM 8: docs/legal/PRIVACY_PHONE_HOME.md discloses heartbeat fields + opt-out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python <3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]

import yaml

REPO = Path(__file__).resolve().parents[3]

README = REPO / "README.md"
NOTICE = REPO / "NOTICE.md"
LANDING_PKG = REPO / "core" / "landing" / "package.json"
BACKEND_PYPROJECT = REPO / "core" / "backend" / "pyproject.toml"
TRADEMARKS = REPO / "docs" / "legal" / "TRADEMARKS.md"
PRIVACY_PHONE_HOME = REPO / "docs" / "legal" / "PRIVACY_PHONE_HOME.md"
SBOM_WF = REPO / ".github" / "workflows" / "sbom.yml"
LICENSE_CHECK_WF = REPO / ".github" / "workflows" / "license-check.yml"


# --- ITEM 1: README badge + License section use BUSL-1.1 ---------------------


def test_item1_readme_badge_uses_busl_not_bsl():
    body = README.read_text(encoding="utf-8")
    assert "License-BUSL--1.1" in body, "README badge missing BUSL-1.1 SPDX id"
    assert "License-BSL%201.1" not in body, "stale 'BSL 1.1' badge still present"


def test_item1_readme_license_section_names_busl_spdx():
    body = README.read_text(encoding="utf-8")
    # Heading + SPDX both required.
    assert "## License" in body
    assert "BUSL-1.1" in body, "README License section missing SPDX id BUSL-1.1"
    # The literal short form "(BSL)" stand-alone must not survive.
    assert "Source License 1.1** (BSL)" not in body, (
        "stale '(BSL)' parenthetical remains in README License section"
    )


# --- ITEM 2: NOTICE.md ------------------------------------------------------


def test_item2_notice_md_exists_and_has_required_blocks():
    assert NOTICE.exists(), "NOTICE.md is missing at repo root"
    body = NOTICE.read_text(encoding="utf-8")
    for needle in (
        "Automatia ABS",
        "Copyright",
        "Automatia BCN",
        "BUSL-1.1",
        "Change Date",
        "2030-05-07",
        "TRADEMARKS",
        "Automatia BCN",
        "THIRD-PARTY COMPONENTS",
        "docs/legal/THIRD_PARTY_LICENSES.md",
    ):
        assert needle in body, f"NOTICE.md missing required content: {needle}"


def test_item2_notice_md_references_apache_2_post_change_date():
    body = NOTICE.read_text(encoding="utf-8")
    assert "Apache License 2.0" in body, (
        "NOTICE.md must disclose the Change Date conversion target (Apache 2.0)"
    )


# --- ITEM 3: machine-readable license metadata ------------------------------


def test_item3_landing_package_json_license_busl():
    payload = json.loads(LANDING_PKG.read_text(encoding="utf-8"))
    assert payload.get("license") == "BUSL-1.1", (
        f"core/landing/package.json license must be 'BUSL-1.1', got {payload.get('license')!r}"
    )


def test_item3_backend_pyproject_license_busl():
    payload = tomllib.loads(BACKEND_PYPROJECT.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    license_field = project.get("license")
    # PEP 621 supports either {text = "..."} table or a plain string.
    if isinstance(license_field, dict):
        assert license_field.get("text") == "BUSL-1.1", (
            f"pyproject.toml [project].license.text must be 'BUSL-1.1', got {license_field}"
        )
    else:
        assert license_field == "BUSL-1.1", (
            f"pyproject.toml [project].license must be 'BUSL-1.1', got {license_field!r}"
        )


# --- ITEM 4: TRADEMARKS.md --------------------------------------------------


def test_item4_trademarks_md_exists_and_has_fossmarks_sections():
    assert TRADEMARKS.exists(), "docs/legal/TRADEMARKS.md missing"
    body = TRADEMARKS.read_text(encoding="utf-8")
    lower = body.lower()
    # Section anchors / topics required by the FOSSmarks-style policy.
    required_topics = [
        "automatia bcn",
        "automatia abs",
        "nominative fair use",
        "permission",
        "reporting",
        "support@automatiabcn.com",
    ]
    for topic in required_topics:
        assert topic in lower, f"TRADEMARKS.md missing topic: {topic}"


def test_item4_trademarks_md_distinguishes_marks_from_code_license():
    body = TRADEMARKS.read_text(encoding="utf-8").lower()
    # Policy must explicitly say trademarks are separate from BUSL/Apache.
    assert "trademark" in body
    assert ("busl" in body) or ("business source" in body)
    assert "apache" in body, (
        "TRADEMARKS.md must explain that Apache 2.0 conversion does not relicense marks"
    )


# --- ITEM 5: README OSI distinction disclosure ------------------------------


def test_item5_readme_discloses_not_osi_open_source():
    body = README.read_text(encoding="utf-8").lower()
    assert "source-available" in body, "README missing 'source-available' disclosure"
    assert "osi" in body, "README missing OSI distinction disclosure"
    # Must explain the post-Change-Date Apache 2.0 conversion in the same area.
    assert "apache license 2.0" in body or "apache 2.0" in body


# --- ITEM 6: SBOM CI workflow ----------------------------------------------


def test_item6_sbom_workflow_exists_and_runs_on_release():
    assert SBOM_WF.exists(), ".github/workflows/sbom.yml missing"
    wf = yaml.safe_load(SBOM_WF.read_text(encoding="utf-8"))
    triggers = wf.get(True) or wf.get("on") or {}
    assert "release" in triggers, "SBOM workflow must trigger on GitHub Release"
    assert "workflow_dispatch" in triggers, (
        "SBOM workflow must support manual workflow_dispatch"
    )


def test_item6_sbom_workflow_runs_cyclonedx_for_both_ecosystems():
    body = SBOM_WF.read_text(encoding="utf-8")
    assert "cyclonedx-npm" in body, "SBOM workflow missing npm CycloneDX generator"
    assert "cyclonedx-py" in body or "cyclonedx-bom" in body, (
        "SBOM workflow missing pip CycloneDX generator"
    )
    assert "artifacts/sbom/abs-landing.cdx.json" in body
    assert "artifacts/sbom/abs-backend.cdx.json" in body


def test_item6_sbom_workflow_uploads_artifact():
    body = SBOM_WF.read_text(encoding="utf-8")
    assert "actions/upload-artifact" in body, (
        "SBOM workflow must upload SBOM artifact for retention"
    )


# --- ITEM 7: license-check.yml ----------------------------------------------


def test_item7_license_check_workflow_exists_with_threshold():
    assert LICENSE_CHECK_WF.exists(), ".github/workflows/license-check.yml missing"
    body = LICENSE_CHECK_WF.read_text(encoding="utf-8")
    assert "licensee" in body, "license-check workflow does not call licensee"
    assert "--confidence=90" in body, (
        "license-check workflow must enforce >=90% confidence threshold"
    )


def test_item7_license_check_workflow_paths_scoped():
    wf = yaml.safe_load(LICENSE_CHECK_WF.read_text(encoding="utf-8"))
    triggers = wf.get(True) or wf.get("on") or {}
    # Both pull_request + push to main must scope on LICENSE / NOTICE changes.
    pr = triggers.get("pull_request", {})
    push = triggers.get("push", {})
    for trigger_name, trigger_cfg in (("pull_request", pr), ("push", push)):
        paths = trigger_cfg.get("paths", [])
        assert "LICENSE" in paths, (
            f"license-check.yml {trigger_name} must scope on LICENSE changes"
        )
        assert "NOTICE.md" in paths, (
            f"license-check.yml {trigger_name} must scope on NOTICE.md changes"
        )


# --- ITEM 8: PRIVACY_PHONE_HOME.md ------------------------------------------


def test_item8_phone_home_doc_discloses_fields_and_opt_out():
    assert PRIVACY_PHONE_HOME.exists(), "docs/legal/PRIVACY_PHONE_HOME.md missing"
    body = PRIVACY_PHONE_HOME.read_text(encoding="utf-8")
    # All five field names from the heartbeat manifest must be disclosed.
    for field in ("jti", "machine_fp", "build_hash", "instance_url"):
        assert field in body, (
            f"PRIVACY_PHONE_HOME.md must disclose heartbeat field: {field}"
        )
    # Endpoint URL + opt-out env var both required.
    assert "abs-license-activation.automatiaabs.workers.dev" in body
    assert "ABS_LICENSE_GATE_DISABLED=1" in body, (
        "PRIVACY_PHONE_HOME.md must document the ABS_LICENSE_GATE_DISABLED opt-out"
    )


def test_item8_phone_home_doc_states_no_customer_payload():
    body = PRIVACY_PHONE_HOME.read_text(encoding="utf-8").lower()
    # The doc must state explicitly that no customer payload leaves the host.
    assert (
        "no customer payload" in body
        or "no customer-data" in body
        or ("never leave" in body and "customer" in body)
    ), "PRIVACY_PHONE_HOME.md must state that no customer payload is transmitted"


# --- cross-cutting integrity guard ------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        NOTICE,
        TRADEMARKS,
        PRIVACY_PHONE_HOME,
        SBOM_WF,
        LICENSE_CHECK_WF,
    ],
)
def test_legal_hardening_files_are_non_empty(path: Path):
    assert path.exists(), f"missing: {path}"
    assert path.stat().st_size > 200, f"suspiciously short: {path}"
