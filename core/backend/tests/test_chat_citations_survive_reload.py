# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""An answer that cited its sources must still cite them after a reload.

The bug this locks down was invisible to every existing test and obvious to
anyone using the product: the assistant streams an answer with "[1]", "[4]"
markers and a Sources list underneath, the page rehydrates from the database a
second later, and the Sources list is gone — leaving the markers pointing at
nothing. Nothing errored. The citations had been written into the `tool_calls`
column as part of a pipeline-metadata blob and simply never read back out.

The lesson generalises: a field that is *stored* is not a field that is
*returned*, and the only way to tell the difference is to read it back.
"""

from __future__ import annotations

import json

from app.api.chat import _stored_citations, _stored_tool_calls

CASCADE_BLOB = json.dumps(
    {
        "pipeline": "auto_direct",
        "citations": [
            {"chunk_id": "c1", "source": "falcon-retainer.md", "excerpt": "4,200 EUR"},
            {"chunk_id": "c2", "source": "notes.md", "excerpt": "invoiced monthly"},
        ],
        "fallback_chain": ["groq"],
        "cost_usd": 0.0,
        "free": True,
    }
)

AGENT_BLOB = json.dumps([{"name": "system_status", "args": {}}])


def test_citations_come_back_out_of_the_stored_blob():
    cited = _stored_citations(CASCADE_BLOB)
    assert [c["source"] for c in cited] == ["falcon-retainer.md", "notes.md"]


def test_an_agent_transcript_has_tool_calls_and_no_citations():
    assert _stored_tool_calls(AGENT_BLOB) == [{"name": "system_status", "args": {}}]
    assert _stored_citations(AGENT_BLOB) == []


def test_a_cascade_blob_still_reads_as_one_tool_call_entry():
    # The old shape is a dict, not a list. Existing sessions must keep rendering.
    calls = _stored_tool_calls(CASCADE_BLOB)
    assert len(calls) == 1 and calls[0]["pipeline"] == "auto_direct"


def test_nothing_stored_is_nothing_returned():
    assert _stored_tool_calls(None) == []
    assert _stored_citations(None) == []
    assert _stored_citations("") == []


def test_a_corrupt_blob_does_not_take_the_transcript_down_with_it():
    # A half-written row must cost the user their citations, not their history.
    assert _stored_tool_calls("{not json") == []
    assert _stored_citations("{not json") == []


def test_citations_of_the_wrong_shape_are_dropped_not_forwarded():
    blob = json.dumps({"citations": ["just a string", {"source": "real.md"}]})
    assert _stored_citations(blob) == [{"source": "real.md"}]
