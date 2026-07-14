# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""We were selling a limit that did not exist.

The pricing page offered "5 named operator seats" for $1,196. The licence key
carried a `seat_count`. And `seat_count` appeared in exactly zero decisions: an
admin on the single-seat plan could invite fifty people and nothing anywhere
would so much as log it.

Now that the plan is a monthly subscription priced per seat, the number has to be
real. It is enforced at the only place it can be drawn fairly — the *next*
invitation. People already working keep their accounts: a colleague must not be
locked out of their own server because an invoice bounced.

A pending invitation counts against the total. Otherwise an admin sends ten at
once and walks straight through a limit that only counts the people who have
already accepted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.admin.auth import admin_required
from app.db.models import TenantInvite, User
from app.db.session import get_engine
from app.licensing import seats as seat_gate
from app.main import app

TENANT = "default"


@pytest.fixture()
def client(monkeypatch):
    app.dependency_overrides[admin_required] = lambda: {
        "sub": "admin@example.com",
        "tenant_id": TENANT,
    }
    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "", raising=False)  # a trial
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(admin_required, None)


def _seed_user(email: str) -> None:
    with Session(get_engine()) as db:
        db.add(
            User(
                email=email,
                password_hash="x",
                tenant_slug=TENANT,
                role="admin",
                status="active",
            )
        )
        db.commit()


def test_the_trial_covers_one_person(client) -> None:
    """And says so in words a person can act on, not `seat_limit_reached`."""
    _seed_user("admin@example.com")

    res = client.post(
        "/v1/admin/users/invite",
        json={"email": "colleague@example.com", "role": "operator"},
    )
    assert res.status_code == 402, res.text
    body = res.json()["detail"]
    assert body["error"] == "no_seats_left"
    assert "subscribe to a team plan" in body["message"].lower()
    assert body["seats_licensed"] == 1


def test_an_unaccepted_invitation_is_a_seat(monkeypatch) -> None:
    """Ten invitations at once was the way through a limit that counted only the
    people who had already walked in."""
    monkeypatch.setattr(seat_gate, "licensed_seats", lambda: 3)
    _seed_user("one@example.com")

    with Session(get_engine()) as db:
        db.add(
            TenantInvite(
                invite_id="i-1",
                email="two@example.com",
                role="operator",
                tenant_id=TENANT,
                invited_by="admin",
                magic_token_hash="h",
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                status="pending",
            )
        )
        db.commit()

    seats = seat_gate.status(TENANT)
    assert seats.used == 2, "an invitation that has been sent is a seat given away"
    assert seats.room == 1


def test_a_revoked_invitation_gives_the_seat_back(monkeypatch) -> None:
    monkeypatch.setattr(seat_gate, "licensed_seats", lambda: 2)
    _seed_user("one@example.com")

    with Session(get_engine()) as db:
        db.add(
            TenantInvite(
                invite_id="i-2",
                email="gone@example.com",
                role="operator",
                tenant_id=TENANT,
                invited_by="admin",
                magic_token_hash="h",
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                status="revoked",
            )
        )
        db.commit()

    assert seat_gate.status(TENANT).used == 1


def test_re_inviting_someone_does_not_cost_a_second_seat(client) -> None:
    """A duplicate invitation is not a new person.

    The seat gate first ran before the duplicate check, so an admin whose seats
    were full and who re-invited someone they had *already* invited was told to
    buy a seat — for a person who was already occupying one. The gate belongs at
    the moment an invitation would genuinely add somebody.
    """
    _seed_user("admin@example.com")
    with Session(get_engine()) as db:
        db.add(
            TenantInvite(
                invite_id="i-dupe",
                email="colleague@example.com",
                role="operator",
                tenant_id=TENANT,
                invited_by="admin",
                magic_token_hash="h",
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                status="pending",
            )
        )
        db.commit()

    res = client.post(
        "/v1/admin/users/invite",
        json={"email": "colleague@example.com", "role": "operator"},
    )

    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"] == "duplicate_pending_invite"


def test_a_team_licence_lets_the_team_in(monkeypatch, client) -> None:
    monkeypatch.setattr(seat_gate, "licensed_seats", lambda: 5)
    _seed_user("admin@example.com")

    res = client.post(
        "/v1/admin/users/invite",
        json={"email": "colleague@example.com", "role": "operator"},
    )
    assert res.status_code == 201, res.text


def test_a_full_team_is_told_the_numbers(monkeypatch) -> None:
    """ "Seat limit reached" tells an admin nothing they had not guessed. The
    sentence carries the count, what is using it, and what to do."""
    seats = seat_gate.Seats(licensed=5, used=5)
    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "a-real-key", raising=False)

    message = seat_gate.refusal(seats)
    assert message is not None
    assert "5 seats" in message
    assert "5 in use" in message
    assert "invitations that have not been accepted" in message
