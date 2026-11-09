"""Signing up with someone else's email must not touch their account.

`POST /auth/signup` is public, and it wrote to the `users` row for whatever
email it was given. For an address that already had an account that meant: a
new password of the caller's choosing, the caller's tenant, and `pending` in
place of `active`. On a server that echoes the activation link (any `env` other
than the literal "prod"), the caller could then claim the row and be signed in
as that person — including the bootstrap admin, whose credentials file the
claim rewrote.

A signup for a known address now answers like any other signup and does nothing.
"""

from __future__ import annotations

import json

import bcrypt
import pytest
from sqlmodel import Session, select

from app.api import auth as auth_api
from app.config import settings
from app.db.models import User
from app.db.session import get_engine

_REAL_PW = "the-owners-password"
_THEIR_PW = "chosen-by-a-stranger"


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _user(email: str) -> User | None:
    with Session(get_engine()) as db:
        return db.scalars(select(User).where(User.email == email)).first()


def _add_user(email: str, *, status: str, role: str = "admin") -> str:
    hashed = _hash(_REAL_PW)
    with Session(get_engine()) as db:
        db.add(
            User(
                email=email,
                password_hash=hashed,
                tenant_slug="corp",
                role=role,
                status=status,
            )
        )
        db.commit()
    return hashed


def _signup(client, email: str):
    return client.post(
        "/auth/signup",
        json={"email": email, "tenant_slug": "elsewhere", "password": _THEIR_PW},
    )


@pytest.fixture()
def bootstrap_admin():
    """A setup-wizard admin on disk, restored afterwards."""
    path = auth_api._admin_credentials_path()
    saved = path.read_text(encoding="utf-8") if path.is_file() else None
    record = {
        "email": "owner@corp.example",
        "password_hash": _hash(_REAL_PW),
        "tenant_slug": "corp",
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    try:
        yield path, record
    finally:
        if saved is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(saved, encoding="utf-8")


def test_an_active_account_is_left_exactly_as_it_was(client):
    before = _add_user("colleague@corp.example", status="active")

    resp = _signup(client, "colleague@corp.example")

    assert resp.status_code == 201, resp.text
    assert "magic_link" not in resp.json()
    row = _user("colleague@corp.example")
    assert row is not None
    assert (row.status, row.role, row.tenant_slug) == ("active", "admin", "corp")
    assert row.password_hash == before
    assert row.magic_token is None


def test_the_owner_can_still_sign_in_and_the_stranger_cannot(client):
    _add_user("colleague@corp.example", status="active")
    _signup(client, "colleague@corp.example")

    theirs = client.post(
        "/auth/login",
        json={"email": "colleague@corp.example", "password": _THEIR_PW},
    )
    assert theirs.status_code == 401
    mine = client.post(
        "/auth/login",
        json={"email": "colleague@corp.example", "password": _REAL_PW},
    )
    assert mine.status_code == 200, mine.text


def test_a_revoked_account_is_not_revived_by_a_signup(client):
    _add_user("gone@corp.example", status="revoked")

    resp = _signup(client, "gone@corp.example")

    assert "magic_link" not in resp.json()
    assert _user("gone@corp.example").status == "revoked"


@pytest.mark.parametrize("email", ["owner@corp.example", "Owner@Corp.Example"])
def test_the_bootstrap_admin_cannot_be_signed_up_over(client, bootstrap_admin, email):
    path, record = bootstrap_admin

    resp = _signup(client, email)

    assert resp.status_code == 201, resp.text
    assert "magic_link" not in resp.json()
    assert _user(email) is None, "a row was minted for the admin's address"
    assert json.loads(path.read_text(encoding="utf-8")) == record


def test_a_known_address_gets_the_same_answer_as_a_new_one(client):
    """Otherwise the endpoint tells a stranger who has an account here."""
    _add_user("colleague@corp.example", status="active")

    known = _signup(client, "colleague@corp.example")
    fresh = _signup(client, "newcomer@corp.example")

    assert known.status_code == fresh.status_code == 201
    k, f = known.json(), fresh.json()
    f.pop("magic_link", None)
    assert k == f


def test_an_unclaimed_signup_can_still_be_repeated_and_carries_no_role(client):
    """Someone who lost the first link signs up again; that must keep working.
    A pending row is also the one place a role could be carried forward from."""
    _add_user("slow@corp.example", status="pending", role="admin")

    resp = _signup(client, "slow@corp.example")

    assert resp.status_code == 201, resp.text
    row = _user("slow@corp.example")
    assert row.status == "pending"
    assert row.role == "member"
    assert row.magic_token


@pytest.mark.parametrize(
    "env,domain,ssl_mode,expected",
    [
        ("dev", "", "", True),
        ("prod", "", "", False),
        ("production", "", "", False),
        ("Production", "", "", False),
        # A real domain on a public certificate is production whatever `env` says.
        ("dev", "abs.corp.example.com", "acme", False),
    ],
)
def test_the_activation_link_is_only_echoed_on_a_private_box(
    monkeypatch, env, domain, ssl_mode, expected
):
    monkeypatch.setattr(settings, "env", env)
    monkeypatch.setattr(settings, "domain", domain)
    monkeypatch.setattr(settings, "ssl_mode", ssl_mode)
    assert auth_api._may_echo_magic_link() is expected
