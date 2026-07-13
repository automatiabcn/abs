"""030 Modul G — provider_catalog.json schema + content guard."""

from __future__ import annotations

import json
from pathlib import Path

CATALOG = (
    Path(__file__).resolve().parents[1] / "app" / "cascade" / "provider_catalog.json"
)


def test_provider_catalog_loads_as_json():
    data = json.loads(CATALOG.read_text())
    assert "version" in data
    assert isinstance(data.get("providers"), list)
    assert len(data["providers"]) >= 5


def test_provider_catalog_has_all_required_entries():
    data = json.loads(CATALOG.read_text())
    ids = {entry["id"] for entry in data["providers"]}
    must_have = {
        "groq-compound",
        "groq-compound-mini",
        "cerebras-qwen-235b",
        "gemini-flash-latest",
        "gemini-pro-latest",
    }
    missing = must_have - ids
    assert not missing, f"missing provider entries: {missing}"


def test_provider_catalog_version_is_iso_date():
    import re

    data = json.loads(CATALOG.read_text())
    version = data.get("version")
    assert isinstance(version, str)
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", version), (
        f"version must be ISO date YYYY-MM-DD, got: {version!r}"
    )


def test_provider_catalog_tier_values_are_valid():
    data = json.loads(CATALOG.read_text())
    valid_tiers = {"agentic", "upper", "auto-upgrade", "fast", "code", "free"}
    for entry in data["providers"]:
        assert entry["tier"] in valid_tiers, (
            f"unknown tier '{entry['tier']}' on {entry['id']}"
        )
        assert isinstance(entry["context"], int) and entry["context"] > 0
        assert "added" in entry
