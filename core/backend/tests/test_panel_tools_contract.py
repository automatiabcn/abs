"""Q12 R75 (S8) — /v1/panel/tools contract + edge-case deep.

R70 migrated /panel home to a server-side split-shell that fetches
/v1/panel/tools (along with /v1/system/quota_status and
/v1/panel/cascade/recent) with the caller's session cookie
forwarded. The endpoint is now on the SSR critical path: a
regression in the response shape, the per-tool keys, the category
filter, or the sort order breaks the first paint of the panel home
StatCards + bar chart.

The only existing test for /v1/panel/tools is one assertion in
`test_tools_count.py::test_core_tool_names_registered` that checks
the registry, not the HTTP endpoint shape. R75 fills the gap with
8 contract tests:

- response shape {total, filtered_count, category_counts, tools}
- tools is a list and category_counts is a dict
- per-tool keys (name, description, category, input_schema)
- input_schema has {required: list, properties: list}
- ?category= narrows the filtered set (every row matches)
- unknown ?category= returns 0 filtered + empty category_counts
- ?category= does NOT change `total` (full registry size)
- tools sorted by (category, name)
"""

from __future__ import annotations

import pytest

from app.api.auth import current_admin
from app.main import app


@pytest.fixture(autouse=True)
def _signed_in():
    """The panel forwards the caller's session cookie, as the note above says.

    These tests never sent one — the route was open, so nothing made them. It is
    not open any more (a stranger could pull the whole tool catalogue off a
    customer's server), so they sign in like the panel does. The contract they
    assert on is unchanged; only the doorway is.
    """
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@local"}
    yield
    app.dependency_overrides.pop(current_admin, None)


def _get(client, path: str):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    return r.json()


def test_response_shape_contract(client):
    body = _get(client, "/v1/panel/tools")
    assert set(body.keys()) >= {
        "total",
        "filtered_count",
        "category_counts",
        "tools",
    }


def test_types_match_client_expectations(client):
    body = _get(client, "/v1/panel/tools")
    assert isinstance(body["total"], int)
    assert isinstance(body["filtered_count"], int)
    assert isinstance(body["category_counts"], dict)
    assert isinstance(body["tools"], list)


def test_per_tool_keys_present(client):
    body = _get(client, "/v1/panel/tools")
    if not body["tools"]:
        # No tools registered in this test build is allowed (mcp
        # server can be a stub). The shape contract still holds.
        return
    expected = {"name", "description", "category", "input_schema"}
    for tool in body["tools"]:
        assert expected <= set(tool.keys()), tool


def test_input_schema_shape(client):
    """Each tool's `input_schema` is summarised as `{required, properties}`
    so the panel can render param chips without parsing JSON Schema.
    Both fields are lists."""
    body = _get(client, "/v1/panel/tools")
    for tool in body["tools"]:
        sch = tool["input_schema"]
        assert isinstance(sch, dict)
        assert isinstance(sch.get("required"), list), tool["name"]
        assert isinstance(sch.get("properties"), list), tool["name"]


def test_category_filter_narrows_rows(client):
    """When `?category=provider` is passed, every returned tool row
    must carry that category."""
    full = _get(client, "/v1/panel/tools")
    categories_present = {t["category"] for t in full["tools"]}
    if not categories_present:
        return  # empty registry — filter test inapplicable
    cat = next(iter(categories_present))
    filtered = _get(client, f"/v1/panel/tools?category={cat}")
    assert filtered["filtered_count"] == len(filtered["tools"])
    for t in filtered["tools"]:
        assert t["category"] == cat


def test_unknown_category_returns_empty_filtered(client):
    body = _get(client, "/v1/panel/tools?category=__not_a_category__")
    assert body["filtered_count"] == 0
    assert body["tools"] == []
    assert body["category_counts"] == {}


def test_total_is_unfiltered(client):
    """`total` must reflect the full registry, regardless of any
    `?category=` filter — the panel uses it for the "MCP Tools"
    StatCard headline number."""
    full = _get(client, "/v1/panel/tools")
    filtered = _get(client, "/v1/panel/tools?category=__not_a_category__")
    assert full["total"] == filtered["total"]


def test_sort_by_category_then_name(client):
    """Tools sorted by `(category, name)`. The panel chart depends
    on a stable iteration order so two adjacent renders don't shuffle
    the bars."""
    body = _get(client, "/v1/panel/tools")
    pairs = [(t["category"], t["name"]) for t in body["tools"]]
    assert pairs == sorted(pairs), pairs[:5]
