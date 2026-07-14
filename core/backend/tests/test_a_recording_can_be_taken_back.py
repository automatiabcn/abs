# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""There was no way to delete a recording.

A person uploads a conversation — the wrong file, the wrong meeting, a client who
has since asked to be forgotten — and the product transcribes it, indexes it, and
answers questions out of it. Forever. An uploaded *document* could be deleted
(`/v1/rag/documents/{doc_id}`); the recording of an actual conversation between
actual people could not, which is exactly the wrong way round.

Deleting the row is not deleting the recording. If the chunks stay in the vector
store, the meeting still answers questions — and having been told it was deleted
is worse than never having asked, because now nobody is looking. So the chunks go
first, and if the store will not answer, the endpoint refuses and says so instead
of removing the transcript and leaving the searchable copy behind.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import app.api.meetings as meetings_mod
from app.api.auth import current_admin
from app.main import app


@pytest.fixture()
def client():
    app.dependency_overrides[current_admin] = lambda: {"sub": "admin@abs.local"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(current_admin, None)


def _upload(client: TestClient, monkeypatch, name: str = "standup.wav") -> int:
    async def _fake_transcribe(path):  # noqa: ANN001
        return {
            "language": "en",
            "duration_sec": 60.0,
            "backend": "mock",
            "summary": "the rent is due on the fifth",
            "speakers": ["S1"],
            "segments": [
                {
                    "speaker_id": "S1",
                    "start": 0.0,
                    "end": 60.0,
                    "text": "the rent is due on the fifth of every month, agreed",
                }
            ],
        }

    monkeypatch.setattr(meetings_mod, "transcribe_path", _fake_transcribe)
    monkeypatch.setattr(meetings_mod, "_autoindex_meeting_rag", lambda **_: 1)
    monkeypatch.setattr(meetings_mod, "_indexed_chunk_count", lambda _m: 1)

    resp = client.post(
        "/v1/meetings/upload",
        files={"audio": (name, io.BytesIO(b"RIFF" + b"\0" * 2048), "audio/wav")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_deleting_a_meeting_takes_the_chunks_with_it(client, monkeypatch) -> None:
    meeting_id = _upload(client, monkeypatch)

    deleted_docs: list[str] = []

    def _delete_document(*, collection, tenant_id, doc_id, project_id=None):  # noqa: ANN001
        deleted_docs.append(doc_id)
        return 1

    from app.rag import qdrant_client as qc

    monkeypatch.setattr(qc, "delete_document", _delete_document, raising=True)

    resp = client.delete(f"/v1/meetings/{meeting_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True

    # The searchable copy is what makes a meeting answerable. It went.
    assert deleted_docs, "the transcript was deleted and its chunks were left behind"

    # And the meeting itself is gone, not merely hidden.
    assert client.get(f"/v1/meetings/{meeting_id}").status_code == 404
    assert all(
        m["id"] != meeting_id for m in client.get("/v1/meetings").json()["meetings"]
    )


def test_if_the_chunks_cannot_be_removed_nothing_is(client, monkeypatch) -> None:
    """The dangerous half-success, refused.

    A transcript deleted out of SQL while its chunks stay in the vector store is
    the worst of both: the operator is told the recording is gone, the recording
    still answers questions, and there is no longer a row to find it by.
    """
    meeting_id = _upload(client, monkeypatch, name="private.wav")

    from app.rag import qdrant_client as qc

    def _boom(**_):  # noqa: ANN001
        raise RuntimeError("qdrant is down")

    monkeypatch.setattr(qc, "delete_document", _boom, raising=True)

    resp = client.delete(f"/v1/meetings/{meeting_id}")
    assert resp.status_code == 503, resp.text
    assert "still in the knowledge base" in resp.text

    # Nothing was removed, and the operator can try again.
    assert client.get(f"/v1/meetings/{meeting_id}").status_code == 200


def test_a_meeting_in_another_tenant_is_not_yours_to_delete(
    client, monkeypatch
) -> None:
    meeting_id = _upload(client, monkeypatch)

    app.dependency_overrides[current_admin] = lambda: {"sub": "someone@else.com"}
    monkeypatch.setattr(meetings_mod, "_admin_tenant", lambda _a: "other-tenant")

    resp = client.delete(f"/v1/meetings/{meeting_id}")
    assert resp.status_code == 404
