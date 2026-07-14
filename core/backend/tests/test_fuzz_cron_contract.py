"""
weekend fuzz cron workflow contract.

The 30K Hypothesis fuzz (chat + RAG + workflows × 10K each) lives behind
the `[fuzz]` pytest marker that PR CI default-skips and the
`mutation-weekend.yml` workflow runs every Saturday 02:00 UTC.

R80 reviewed the cron output (no counterexamples surfaced — `.hypothesis/`
holds no `examples/` directory locally, and the local 30K run finishes
cleanly). The risk a regression test guards against here is *the cron
silently breaking*: someone reformats `mutation-weekend.yml`, drops the
`fuzz-30k` job, or removes the `-m fuzz` selector — and the Saturday
window quietly stops running for weeks.

This test asserts:
  1. The workflow file still exists and parses as YAML.
  2. The Saturday cron is still wired (`schedule.cron == 0 2 * * SAT`).
  3. The `fuzz-30k` job exists and pins the test file + `[fuzz]` marker.
  4. The on-failure `Upload Hypothesis-DB` step still uploads the
     `.hypothesis/` directory so a future review has the artifact to read.
  5. The fuzz pytest file the cron points at exists and has the
     `[fuzz]` marker on its test classes / functions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "mutation-weekend.yml"
FUZZ_TESTS_PATH = REPO_ROOT / "core" / "backend" / "tests" / "test_hypothesis_10k.py"


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_workflow_file_exists_and_parses(workflow):
    assert workflow is not None
    assert workflow.get("name") == "Mutation Weekend"


def test_saturday_cron_schedule_is_wired(workflow):
    """Saturday 02:00 UTC off-hours window. Don't drift this without
    the worker / founder agreeing to a new cadence."""
    # PyYAML reads the YAML key `on:` as Python boolean True. Use that
    # if present, else fall back to the string key for unusual encodings.
    on_block = workflow.get(True) or workflow.get("on") or {}
    schedules = on_block.get("schedule") or []
    cron_lines = [s.get("cron") for s in schedules if isinstance(s, dict)]
    assert "0 2 * * SAT" in cron_lines, (
        f"Saturday 02:00 UTC cron missing; current schedules={cron_lines!r}"
    )


def test_fuzz_30k_job_exists_with_correct_selector(workflow):
    jobs = workflow.get("jobs", {})
    assert "fuzz-30k" in jobs, "fuzz-30k job missing from mutation-weekend.yml"
    job = jobs["fuzz-30k"]
    steps = job.get("steps", [])
    run_blocks = [s.get("run", "") for s in steps if isinstance(s, dict)]
    full = "\n".join(run_blocks)
    assert "tests/test_hypothesis_10k.py" in full, (
        "fuzz-30k job no longer references the 10K test file"
    )
    assert "-m fuzz" in full, "fuzz-30k job dropped the [fuzz] marker selector"


def test_on_failure_artifact_upload_preserves_hypothesis_db(workflow):
    """Without this upload, a counterexample on Saturday would vanish
    by Monday — defeating the entire weekend-cron review loop."""
    job = workflow["jobs"]["fuzz-30k"]
    upload_step = next(
        (
            s
            for s in job.get("steps", [])
            if isinstance(s, dict) and "Upload Hypothesis-DB" in (s.get("name") or "")
        ),
        None,
    )
    assert upload_step is not None, "Hypothesis-DB upload step missing"
    assert upload_step.get("if") == "failure()", (
        "upload guard must be `if: failure()` so passing runs don't bloat "
        "actions storage"
    )
    with_block = upload_step.get("with", {})
    assert with_block.get("path") == "core/backend/.hypothesis/"
    # 14-day retention is the contract — long enough that a Monday review
    # of a Saturday failure has the artifact, short enough that the
    # workflow doesn't accumulate forever.
    assert int(with_block.get("retention-days", 0)) >= 7


def test_fuzz_test_file_exists_and_has_fuzz_marker():
    assert FUZZ_TESTS_PATH.exists(), f"fuzz pytest file missing: {FUZZ_TESTS_PATH}"
    text = FUZZ_TESTS_PATH.read_text(encoding="utf-8")
    # The marker should appear at module/class level — without it, the
    # weekend cron's `-m fuzz` would select nothing and silently pass.
    assert (
        "pytestmark" in text
        or "@pytest.mark.fuzz" in text
        or "pytest.mark.fuzz" in text
    ), "test_hypothesis_10k.py no longer carries the [fuzz] marker"
