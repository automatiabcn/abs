# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Tenant isolation is on unless someone turns it off.

`multi_tenant_strict` defaulted to False. It guards the paths where one customer
could reach another's data — installing a plugin under an arbitrary `tenant=` value,
raw Cypher that returns scalars past the row filter — and it shipped open, with the
operator expected to know to close it. That is the wrong way round for a setting whose
failure mode is a customer reading another customer's rows.

The old test pinned the default down as correct behaviour, which is worth naming: a
test can assert a fail-open default as confidently as a fail-closed one, and the green
tick looks the same either way.

Turning it on has a cost, and it is the reason it stayed off: the raw-Cypher console
was refused whenever the flag was set, which would have taken /admin/graph away from
every single-tenant self-hoster. So the refusal is now tied to the thing that actually
makes raw Cypher dangerous — a second tenant existing — rather than to the flag.
"""

from __future__ import annotations

from app.config import Settings
from app.api import graph as graph_api


def test_isolation_is_on_by_default():
    """A fresh install protects its tenants without being asked to."""
    assert Settings().multi_tenant_strict is True


def test_a_single_tenant_self_host_keeps_its_raw_cypher_console(monkeypatch):
    """The console is a tool the owner of the data is entitled to. There is no
    second customer on this server to leak to."""
    monkeypatch.setattr(graph_api.settings, "multi_tenant_strict", True)
    monkeypatch.setattr(graph_api, "_serves_more_than_one_tenant", lambda: False)

    graph_api._refuse_raw_cypher_if_shared()  # does not raise


def test_a_shared_server_refuses_raw_cypher(monkeypatch):
    """`RETURN n.email AS e` carries no tenant_id key and walks straight past the
    row filter. On a server with more than one customer on it, that is the leak."""
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(graph_api.settings, "multi_tenant_strict", True)
    monkeypatch.setattr(graph_api, "_serves_more_than_one_tenant", lambda: True)

    with pytest.raises(HTTPException) as exc:
        graph_api._refuse_raw_cypher_if_shared()
    assert exc.value.status_code == 403


def test_when_the_tenant_count_cannot_be_read_we_assume_the_worst(monkeypatch):
    """A database we cannot ask is not a database with one tenant in it."""

    def _boom():
        raise RuntimeError("db is down")

    monkeypatch.setattr(
        graph_api,
        "_serves_more_than_one_tenant",
        graph_api._serves_more_than_one_tenant,
    )
    monkeypatch.setattr("app.db.session.get_engine", _boom)

    assert graph_api._serves_more_than_one_tenant() is True
