"""Q11-L13 Round 44 — Hypothesis property-based fuzz scaled to 10K examples.

S6 R39 shipped 1K examples per surface (3K total) as the
engineering tradeoff. R44 scales the tradeoff target up to 10K
per surface (30K total) but gates the suite under
`@pytest.mark.fuzz` so it is **default-skipped** in normal CI:

  pytest                      → skips this file (1633 PASS path)
  pytest -m fuzz               → runs only this file
  pytest -m "fuzz or not fuzz" → runs everything

Use the marker mode for the weekend mutation cron (R41) — the
same `mutation-weekend.yml` job can pick this up by passing
`-m fuzz` after the mutmut step.

Same contract as R39:
  * NEVER 5xx
  * status ∈ {200, 400, 401, 403, 404, 409, 415, 422, 429}
  * /v1/rag and /v1/workflows additionally allow 503
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st


VALID_ROLES = ("user", "assistant", "system", "tool")
ACCEPTABLE_STATUS = {200, 400, 401, 403, 404, 409, 415, 422, 429}


@pytest.fixture()
def admin_client(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200
    return client


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    from app.config import settings as app_settings

    monkeypatch.setattr(
        app_settings, "anthropic_mock_mode", "ok", raising=False
    )


@pytest.fixture(autouse=True)
def _cleanup_chat_sessions():
    yield
    from sqlmodel import Session, delete
    from app.db.models import ChatMessage, ChatSession
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        db.execute(delete(ChatMessage))
        db.execute(delete(ChatSession))
        db.commit()


@st.composite
def chat_message(draw):
    role = draw(
        st.one_of(
            st.sampled_from(VALID_ROLES),
            st.text(min_size=0, max_size=20),
            st.lists(st.text(), min_size=0, max_size=3),
            st.integers(min_value=-100, max_value=100),
            st.none(),
        ),
    )
    content = draw(
        st.one_of(
            st.text(min_size=0, max_size=8500),
            st.binary(min_size=0, max_size=200).map(
                lambda b: b.decode("utf-8", errors="replace"),
            ),
            st.lists(st.text(), max_size=4),
            st.none(),
        ),
    )
    msg = {}
    if role is not None:
        msg["role"] = role
    if content is not None:
        msg["content"] = content
    return msg


# Common settings — 10K examples, no deadline, suppress slow-fixture
# warnings (the FastAPI client + DB cleanup is intrinsically slow).
HEAVY_SETTINGS = settings(
    max_examples=10_000,
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ],
    derandomize=False,
)


@pytest.mark.fuzz
class TestQ11L13ChatCompletions10K:
    @HEAVY_SETTINGS
    @given(
        messages=st.lists(chat_message(), min_size=0, max_size=8),
        session_id=st.one_of(
            st.none(),
            st.integers(min_value=-(2**63), max_value=2**63 - 1),
            st.text(max_size=10),
        ),
    )
    def test_chat_completions_no_5xx_10k(
        self, admin_client, messages, session_id
    ):
        body = {"messages": messages}
        if session_id is not None:
            body["session_id"] = session_id
        r = admin_client.post("/v1/chat/completions", json=body)
        assert r.status_code != 500, f"500 on body={body!r}, resp={r.text[:200]}"
        assert r.status_code in ACCEPTABLE_STATUS, (
            f"unexpected status {r.status_code} on body={body!r}"
        )


@pytest.mark.fuzz
class TestQ11L13RagQuery10K:
    @HEAVY_SETTINGS
    @given(
        query=st.one_of(
            st.text(min_size=0, max_size=5000),
            st.binary(min_size=0, max_size=200).map(
                lambda b: b.decode("utf-8", errors="replace"),
            ),
            st.none(),
        ),
        top_k=st.one_of(
            st.none(),
            st.integers(min_value=-100, max_value=10_000),
            st.text(max_size=8),
        ),
        rerank=st.one_of(
            st.booleans(),
            st.text(max_size=8),
            st.none(),
        ),
    )
    def test_rag_query_no_5xx_10k(self, admin_client, query, top_k, rerank):
        body = {}
        if query is not None:
            body["query"] = query
        if top_k is not None:
            body["top_k"] = top_k
        if rerank is not None:
            body["rerank"] = rerank
        r = admin_client.post("/v1/rag/query", json=body)
        assert r.status_code != 500, (
            f"500 on body={body!r}, resp={r.text[:200]}"
        )
        assert r.status_code in ACCEPTABLE_STATUS | {503}, (
            f"unexpected status {r.status_code} on body={body!r}"
        )


@pytest.mark.fuzz
class TestQ11L13WorkflowsSynth10K:
    @HEAVY_SETTINGS
    @given(
        name=st.one_of(st.text(min_size=0, max_size=300), st.none()),
        nl_request=st.one_of(
            st.text(min_size=0, max_size=2000),
            st.binary(min_size=0, max_size=200).map(
                lambda b: b.decode("utf-8", errors="replace"),
            ),
            st.none(),
        ),
    )
    def test_workflows_synth_no_5xx_10k(self, admin_client, name, nl_request):
        body = {}
        if name is not None:
            body["name"] = name
        if nl_request is not None:
            body["nl_request"] = nl_request
        r = admin_client.post("/v1/workflows/synthesize", json=body)
        assert r.status_code != 500, (
            f"500 on body={body!r}, resp={r.text[:200]}"
        )
        assert r.status_code in ACCEPTABLE_STATUS | {503}, (
            f"unexpected status {r.status_code} on body={body!r}"
        )
