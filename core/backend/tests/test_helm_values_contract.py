"""
helm umbrella values contract regression.

Locks the fix from R76 where `cerbos.env` was a map (`{CERBOS_NO_TELEMETRY: "1"}`)
that the cerbos subchart silently dropped (subchart expects a list of
`{name, value}` entries). The map form ALSO defeated caveat #12 telemetry-off in
production, because the env var never reached the cerbos pod — only the umbrella's
backend-configmap was reading it via `.Values.cerbos.env.CERBOS_NO_TELEMETRY`,
which is a backend-side variable that the cerbos process itself does not see.

Regression contract:
1. `cerbos.env` MUST be a list (so it propagates into the cerbos subchart pod env).
2. CERBOS_NO_TELEMETRY entry MUST be present and "1" (caveat #12).
3. backend-configmap.yaml MUST NOT use `.Values.cerbos.env.` map access — that
   stops parsing the moment env is a list.
"""

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
VALUES_PATH = REPO_ROOT / "infra" / "helm" / "abs" / "values.yaml"
BACKEND_CONFIGMAP_PATH = (
    REPO_ROOT / "infra" / "helm" / "abs" / "templates" / "backend-configmap.yaml"
)


@pytest.fixture(scope="module")
def values():
    return yaml.safe_load(VALUES_PATH.read_text(encoding="utf-8"))


def test_cerbos_env_is_list_not_map(values):
    cerbos = values.get("cerbos", {})
    env = cerbos.get("env")
    assert isinstance(env, list), (
        "cerbos.env must be a list of {name, value} entries — the cerbos subchart "
        "expects `env: []` and silently drops a map (R76 regression)."
    )
    for entry in env:
        assert isinstance(entry, dict), f"each entry must be a mapping, got {entry!r}"
        assert {"name", "value"} <= set(entry.keys()), (
            f"each entry must have name+value, got keys={list(entry.keys())}"
        )


def test_cerbos_no_telemetry_caveat_12_enforced(values):
    env = values["cerbos"]["env"]
    matches = [e for e in env if e.get("name") == "CERBOS_NO_TELEMETRY"]
    assert matches, "CERBOS_NO_TELEMETRY missing — caveat #12 not enforced"
    assert matches[0]["value"] == "1", (
        f"CERBOS_NO_TELEMETRY must be '1', got {matches[0]['value']!r}"
    )


def test_backend_configmap_no_map_access_on_cerbos_env():
    text = BACKEND_CONFIGMAP_PATH.read_text(encoding="utf-8")
    assert ".Values.cerbos.env." not in text, (
        "backend-configmap.yaml uses `.Values.cerbos.env.<key>` map access — this "
        "fails template render whenever cerbos.env is a list (the cerbos subchart's "
        "actual schema). R76 removed this access; do not reintroduce."
    )
