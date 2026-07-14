# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Lighthouse slow-3g config sanity.

Pre-2E the slow-3g LHCI profile used `preset: "perf"`, which tells
Lighthouse to run only the performance audits. But the assertion block
still asserts `categories:accessibility` (error gate) — that category
never executes under `preset: perf`, so LHCI emits
`categories.accessibility failure for auditRan assertion` and the job
goes red.

The fix is to drop the preset and explicitly list `onlyCategories`
including accessibility + best-practices. These tests lock in the
correctness of the config so a future drift puts the gate back red
immediately on PR rather than on the next nightly cron.
"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "core" / "landing" / "lighthouserc.slow-3g.json"


def _load() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def test_slow3g_config_exists() -> None:
    assert CONFIG_PATH.is_file(), f"missing: {CONFIG_PATH}"


def test_slow3g_drops_perf_preset() -> None:
    settings = _load()["ci"]["collect"]["settings"]
    # `preset: perf` is the original cause of the
    # auditRan failure. It must NOT come back.
    assert settings.get("preset") != "perf", (
        "preset:perf re-introduced — accessibility audits will not run"
    )


def test_slow3g_includes_accessibility_in_onlyCategories() -> None:
    settings = _load()["ci"]["collect"]["settings"]
    only = settings.get("onlyCategories") or []
    assert "accessibility" in only, (
        "onlyCategories must include 'accessibility' so the asserted "
        "category actually runs"
    )
    assert "performance" in only
    assert "best-practices" in only


def test_slow3g_accessibility_assertion_remains_error_gate() -> None:
    assertions = _load()["ci"]["assert"]["assertions"]
    a11y = assertions.get("categories:accessibility")
    assert a11y is not None, "categories:accessibility assertion removed"
    level, opts = a11y[0], a11y[1]
    assert level == "error", "accessibility must stay error-gated on slow-3g"
    assert opts.get("minScore") == 0.95


def test_slow3g_mobile_form_factor_preserved() -> None:
    settings = _load()["ci"]["collect"]["settings"]
    assert settings["emulatedFormFactor"] == "mobile"
    assert settings["screenEmulation"]["mobile"] is True
