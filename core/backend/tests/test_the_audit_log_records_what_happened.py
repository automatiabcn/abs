# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The audit log has to contain things that happened.

ABS is sold, in the panel's own words, on "what happened on this server and who
did it… every entry is signed and chained… export it for GDPR Article 15 or SOC 2
CC7.2 evidence". For a long time none of that was true, and it took a live run to
see it, because every layer was individually plausible:

* `emit_event` — called from two dozen modules, including login — wrote to a
  Python logger named `abs.audit` that has no handler configured anywhere in the
  codebase. The record reached root, printed the literal string "audit" (no
  formatter reads `extra`), and the payload was discarded. It never went near a
  database.
* The panel and the chain verifier read database tables that essentially nothing
  wrote to.
* When those tables came back empty, the page rendered sample rows — a plausible
  login, a vault read, hmac-looking strings — so the log looked healthy.
* And the verifier reported `ok: true` over zero rows, which is a green light
  that means "I checked nothing".

The whole thing agreed with itself and was wrong. These tests are the ones that
disagree: they do something, and then go looking for it.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.db.models import VaultAuditEntry
from app.db.session import get_engine
from app.observability.audit import emit_event
from app.vault.audit_chain import append_entry, verify_chain


def _rows() -> list[VaultAuditEntry]:
    with Session(get_engine()) as db:
        return list(
            db.scalars(select(VaultAuditEntry).order_by(VaultAuditEntry.id)).all()
        )


def test_an_event_that_is_emitted_can_afterwards_be_read_back():
    """The bridge. This is the test the product did not have."""
    before = len(_rows())

    emit_event(
        None,
        action="auth.login",
        outcome="success",
        user_id="alice@example.com",
        tenant_id="acme",
        path="/v1/admin/login",
    )

    rows = _rows()
    assert len(rows) == before + 1, (
        "an audit event was emitted and the audit log did not grow — this is "
        "exactly the shape of the original bug: the writer and the reader were "
        "not connected to each other"
    )
    entry = rows[-1]
    assert entry.action == "auth.login"
    assert entry.actor == "alice@example.com"
    assert entry.target_key == "/v1/admin/login"


def test_the_recorded_event_is_signed_and_the_chain_still_verifies():
    emit_event(
        None,
        action="provider_key.set",
        outcome="success",
        user_id="alice@example.com",
        provider="groq",
    )

    entry = _rows()[-1]
    assert entry.hmac, "the entry was stored unsigned — it proves nothing"

    result = verify_chain()
    assert result["ok"], f"chain broke at #{result['tampered_entry_id']}"
    assert result["total_entries"] > 0


def test_a_verifier_that_checked_nothing_does_not_get_to_say_intact():
    """`ok: true` over an empty chain is what "I did no work" looks like.

    We do not change that (an empty log genuinely is not tampered with), but the
    panel must never present it as reassurance, so the count is part of the
    contract and the scenario suite asserts on it.
    """
    result = verify_chain()
    assert "total_entries" in result, (
        "verify_chain does not report how much it verified, so 'intact' cannot "
        "be distinguished from 'empty'"
    )


def test_tampering_with_a_stored_row_is_caught():
    """If this fails, the chain is decoration."""
    append_entry(
        action="vault.secret.read",
        actor="alice@example.com",
        target_key="VAULT/groq_api_key",
        detail="before",
    )
    target = _rows()[-1]

    original = target.detail
    with Session(get_engine()) as db:
        row = db.get(VaultAuditEntry, target.id)
        assert row is not None
        row.detail = "after — someone edited the record"
        db.add(row)
        db.commit()

    try:
        result = verify_chain()
        assert result["ok"] is False, "an edited entry sailed through the chain check"
        assert result["tampered_entry_id"] == target.id
    finally:
        # Put it back. These tests share a database, and a chain left broken here
        # is a chain every later test inherits — they would all report tampering
        # and all be right, about this test rather than about themselves.
        with Session(get_engine()) as db:
            row = db.get(VaultAuditEntry, target.id)
            assert row is not None
            row.detail = original
            db.add(row)
            db.commit()


def test_two_events_at_once_do_not_frame_the_log_for_tampering():
    """Concurrency, which is where the chain would have started lying.

    `append_entry` read the last row, inserted, then signed in a *second* commit.
    Two events arriving together both chained off the same predecessor, and the
    verifier — walking in id order — would report the second as tampered with. A
    false accusation is worse than no check: it is the alarm nobody trusts, then
    the alarm nobody turns back on.

    With two rare callers this never fired. It would have fired the day ordinary
    admin activity started being recorded, which is to say: the day the log
    started working.
    """
    import threading

    errors: list[Exception] = []

    def emit(i: int) -> None:
        try:
            emit_event(
                None,
                action="approval.decide",
                outcome="success",
                user_id=f"admin{i}@example.com",
                resource_id=str(i),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=emit, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent audit writes raised: {errors}"

    result = verify_chain()
    assert result["ok"], (
        "twelve events written at the same time left a chain that reads as "
        f"tampered with (first bad row #{result['tampered_entry_id']}) — the log "
        "would be accusing an innocent server of being edited"
    )


def test_no_entry_is_ever_left_unsigned():
    """A row with an empty hmac verifies as tampered with, forever.

    The old two-commit append created exactly that row and left it visible in the
    window between the two commits — and permanently, if the process died in the
    gap.
    """
    for i in range(5):
        emit_event(None, action="rag.query", outcome="success", count=i)

    unsigned = [r.id for r in _rows() if not r.hmac]
    assert unsigned == [], f"entries stored without a signature: {unsigned}"


def test_a_broken_audit_write_never_takes_the_request_down(monkeypatch, caplog):
    """Best-effort, but never silent — a quiet recorder is how this happened."""
    import app.observability.audit as audit_module

    def explode(**_kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr("app.vault.audit_chain.append_entry", explode, raising=True)

    with caplog.at_level("WARNING", logger=audit_module.LOGGER_NAME):
        emit_event(None, action="auth.login", outcome="success", user_id="a@b.co")

    assert any("could not be recorded" in r.message for r in caplog.records), (
        "the audit write failed and said nothing — which is the original sin here"
    )


def test_a_broken_recorder_complains_every_time_but_only_floods_once(
    monkeypatch, caplog
):
    """Loud on every event, but the traceback only once.

    If the database goes away, this fires on every request. A full traceback per
    request buries the very log a person is reading to find out why — but going
    quiet after the first would be the original sin all over again. So: every
    failure is reported, and only the first carries the stack.
    """
    import app.observability.audit as audit_module

    monkeypatch.setattr(audit_module, "_persist_broken", False)
    monkeypatch.setattr(
        "app.vault.audit_chain.append_entry",
        lambda **_kw: (_ for _ in ()).throw(RuntimeError("database is gone")),
        raising=True,
    )

    with caplog.at_level("WARNING", logger=audit_module.LOGGER_NAME):
        for i in range(4):
            emit_event(
                None,
                action="auth.login",
                outcome="success",
                user_id=f"u{i}@example.com",
            )

    complaints = [r for r in caplog.records if "could not be recorded" in r.message]
    assert len(complaints) == 4, "a failed audit write went unreported"

    with_stack = [r for r in complaints if r.exc_info]
    assert len(with_stack) == 1, (
        f"{len(with_stack)} of 4 failures printed a full traceback — an unreachable "
        "database would bury the log in stacks"
    )


def test_the_recorder_rearms_after_it_recovers(monkeypatch, caplog):
    """The next outage has to be diagnosable too, not written off as the last one."""
    import app.observability.audit as audit_module

    monkeypatch.setattr(audit_module, "_persist_broken", True)  # as if already failing

    # A write succeeds — the real append_entry, no patching.
    emit_event(None, action="auth.login", outcome="success", user_id="ok@example.com")
    assert audit_module._persist_broken is False, (
        "the recorder came back and stayed flagged as broken, so the next real "
        "outage would never print a stack trace"
    )


@pytest.mark.parametrize(
    "action,extra",
    [
        ("approval.decide", {"resource_id": "7", "reason": "approve"}),
        ("provider_key.set", {"provider": "groq"}),
        ("provider_key.delete", {"provider": "groq"}),
    ],
)
def test_the_consequential_actions_are_the_ones_being_recorded(action, extra):
    """The three that had no audit call at all.

    Deciding an approval is a person letting a message out of the building.
    Setting a provider key is putting a credential that spends money on the
    server. Deleting one is taking it off. None of them wrote a line.
    """
    before = len(_rows())
    emit_event(
        None, action=action, outcome="success", user_id="alice@example.com", **extra
    )
    rows = _rows()
    assert len(rows) == before + 1
    assert rows[-1].action == action
