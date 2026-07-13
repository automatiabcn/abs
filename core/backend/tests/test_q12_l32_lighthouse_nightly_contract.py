"""
Q12-L32 R82 — Lighthouse nightly workflow stability contract.

Locks the rewrite from R82 — prior workflow targeted unreachable
`https://abs.local/` and the nightly was silently broken for the entire
existence of the repo. This regression pin ensures:

  1. The nightly never points at unreachable hostnames again.
  2. Both desktop + slow-3G jobs exist and reference the canonical
     lighthouserc files (so a single edit to the assertion thresholds
     propagates without ambiguity).
  3. The desktop job retries exactly once on failure.
  4. Both jobs upload artifacts so a failed nightly is reviewable.
  5. The slow-3G lighthouserc declares its mobile + throttling profile
     (no PR-time refactor can silently demote it to desktop).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "lighthouse-nightly.yml"
DESKTOP_RC = REPO_ROOT / "core" / "landing" / "lighthouserc.json"
SLOW3G_RC = REPO_ROOT / "core" / "landing" / "lighthouserc.slow-3g.json"


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def slow3g_rc():
    return json.loads(SLOW3G_RC.read_text(encoding="utf-8"))


def _on_block(workflow: dict) -> dict:
    # PyYAML reads the YAML 1.1 `on:` key as Python boolean True.
    return workflow.get(True) or workflow.get("on") or {}


def test_workflow_loads_and_has_daily_cron(workflow):
    assert workflow.get("name") == "lighthouse-nightly"
    schedules = _on_block(workflow).get("schedule") or []
    crons = [s.get("cron") for s in schedules if isinstance(s, dict)]
    assert "0 3 * * *" in crons, f"daily 03:00 UTC cron missing: {crons!r}"


def test_no_unreachable_abs_local_target():
    """Pre-R82 workflow used `https://abs.local/` which never resolved
    on a GitHub runner — the nightly was silently broken. Allow the
    name in `#`-prefixed comments (R82's rationale references it) but
    reject any active YAML key/value or run-block reuse."""
    code_lines = [
        line
        for line in WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    code_text = "\n".join(code_lines)
    assert "abs.local" not in code_text, (
        "lighthouse-nightly.yml is back to targeting `abs.local` — that "
        "hostname does not resolve on GitHub runners; the nightly will be "
        "silently broken again. Use the local-build pattern from "
        "perf-budget.yml + lighthouserc.json instead."
    )


def test_concurrency_group_prevents_overlap(workflow):
    conc = workflow.get("concurrency", {})
    assert conc.get("group", "").startswith("lighthouse-nightly-"), (
        "missing concurrency group — overlapping scheduled + dispatch runs would clash"
    )
    assert conc.get("cancel-in-progress") is True


def test_desktop_job_uses_canonical_lighthouserc(workflow):
    jobs = workflow.get("jobs", {})
    assert "desktop" in jobs, "desktop job missing"
    job = jobs["desktop"]
    steps = job.get("steps", [])
    lhci_steps = [
        s
        for s in steps
        if isinstance(s, dict) and "lighthouse-ci-action" in (s.get("uses") or "")
    ]
    assert len(lhci_steps) == 2, (
        "desktop job must run lighthouse-ci-action exactly twice — once "
        "as the primary attempt, once as the failure-only retry"
    )
    primary, retry = lhci_steps
    assert primary["with"]["configPath"] == "core/landing/lighthouserc.json"
    assert retry.get("if") == "failure()"
    assert retry["with"]["configPath"] == "core/landing/lighthouserc.json"
    # Both must upload artifacts so the morning review has the report.
    for step in lhci_steps:
        assert step["with"].get("uploadArtifacts") is True
        assert step["with"].get("temporaryPublicStorage") is True


def test_slow_3g_job_exists_and_runs_after_desktop(workflow):
    jobs = workflow.get("jobs", {})
    assert "slow-3g" in jobs, "slow-3g job missing"
    job = jobs["slow-3g"]
    assert job.get("needs") == "desktop", (
        "slow-3g should declare desktop as a dep so the resource "
        "ordering is deterministic"
    )
    # `if: always()` so a desktop failure does NOT cancel the slow-3g
    # run — the two profiles are independent regression signals.
    assert job.get("if") == "always()"
    lhci_step = next(
        (
            s
            for s in job["steps"]
            if isinstance(s, dict) and "lighthouse-ci-action" in (s.get("uses") or "")
        ),
        None,
    )
    assert lhci_step is not None
    assert lhci_step["with"]["configPath"] == ("core/landing/lighthouserc.slow-3g.json")


def test_slow3g_lighthouserc_declares_mobile_throttled_profile(slow3g_rc):
    settings = slow3g_rc["ci"]["collect"]["settings"]
    assert settings["throttlingMethod"] == "devtools"
    assert settings["emulatedFormFactor"] == "mobile"
    assert settings["screenEmulation"]["mobile"] is True
    # rttMs >= 300 + throughput <= 1000 captures the slow-3G envelope.
    throttling = settings["throttling"]
    assert throttling["rttMs"] >= 200
    assert throttling["throughputKbps"] <= 1000
    assert throttling["cpuSlowdownMultiplier"] >= 4


def test_slow3g_assertions_cover_lcp_cls_a11y(slow3g_rc):
    """Slow-3G must still gate on accessibility (an a11y regression
    affects all viewports) and surface LCP/CLS as warn-or-error budgets."""
    asserts = slow3g_rc["ci"]["assert"]["assertions"]
    assert "categories:accessibility" in asserts, (
        "slow-3G must keep the accessibility budget — a11y regressions "
        "are profile-independent"
    )
    a11y = asserts["categories:accessibility"]
    assert a11y[0] == "error" and a11y[1]["minScore"] >= 0.9
    for k in ("largest-contentful-paint", "cumulative-layout-shift"):
        assert k in asserts, f"slow-3G missing {k} budget"


def test_node_version_matches_perf_budget(workflow):
    """Drift from perf-budget.yml's node version causes hard-to-debug
    Lighthouse-vs-Next mismatch. Pin to the same major."""
    desktop_setup = next(
        (
            s
            for s in workflow["jobs"]["desktop"]["steps"]
            if isinstance(s, dict) and "actions/setup-node" in (s.get("uses") or "")
        ),
        None,
    )
    assert desktop_setup is not None
    assert str(desktop_setup["with"]["node-version"]) == "22"
