"""Marketplace egress allowlist matching arms.

NOTE: enforce_egress is an application-level check that is NOT yet wired to a
runtime path — real network egress filtering is a pre-GA requirement (see the
function docstring). These tests pin the MATCHING logic so that when the proxy
that calls it lands, the allow/deny decisions are already correct: no apex
match on a wildcard, no suffix-smuggling, case-insensitive exact match.
"""

import pytest

from app.marketplace.sandbox import EgressDeniedError, SandboxSpec, enforce_egress


def _spec(*allow):
    return SandboxSpec(
        plugin_id="p",
        image="x:1",
        cpu_quota=0.5,
        memory_mb=256,
        network_allowlist=allow,
        read_only_mounts=(),
        tmpfs_mounts=(),
        env={},
        tenant_id="t",
    )


@pytest.mark.parametrize(
    "host",
    ["a.example.com", "sub.a.example.com", "x.EXAMPLE.com", "API.FOO.COM"],
)
def test_allowed_hosts(host):
    enforce_egress(host, _spec("*.example.com", "api.foo.com"))  # no raise


@pytest.mark.parametrize(
    "host",
    [
        "example.com",  # apex must NOT match *.example.com
        "evil-example.com",  # no dot boundary
        "example.com.evil.com",  # suffix smuggling
        "a.example.com.evil.com",
        "aexample.com",
        "notexample.com",
        "foo.com.evil.com",  # exact-pattern suffix smuggling
    ],
)
def test_denied_hosts(host):
    with pytest.raises(EgressDeniedError):
        enforce_egress(host, _spec("*.example.com", "api.foo.com"))


def test_empty_allowlist_denies_all():
    with pytest.raises(EgressDeniedError):
        enforce_egress("anything.com", _spec())
