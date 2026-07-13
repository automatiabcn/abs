# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""ABS_EXTERNAL_MCP_ALLOW_PRIVATE lets you reach your laptop. Not the metadata.

Connecting an external MCP server is a server-side fetch to a URL an admin types,
which makes it a textbook SSRF vector: ABS can reach places the admin's browser
cannot. The guard knew that and blocked private, loopback, link-local, multicast
and reserved addresses.

Then it grew a dev flag — so someone could dogfood against a server on localhost —
and the flag was implemented as an early `return`. It did not relax the private
ranges; it skipped the check. Which silently granted a completely different
permission: 169.254.169.254, the cloud metadata endpoint, which will hand out the
instance's IAM credentials to anything on the box that asks.

"Let me reach my laptop" and "let me reach this machine's credentials" are not the
same request. One flag must not answer both.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.mcp.external.client import ExternalMcpError, _assert_safe_url

# Every cloud's metadata service, plus the general link-local range they live in.
METADATA_URLS = [
    "http://169.254.169.254/latest/meta-data/",          # AWS, GCP, Azure, DO…
    "http://169.254.170.2/v2/credentials/",              # ECS task role
    "http://[fe80::a9fe:a9fe]/",                         # the IPv6 side of the same door
]


@pytest.fixture()
def dev_box(monkeypatch):
    """The dogfood setting, exactly as the local stack runs it."""
    monkeypatch.setattr(settings, "external_mcp_allow_private", True)


@pytest.mark.parametrize("url", METADATA_URLS)
def test_the_metadata_endpoint_is_refused_even_on_a_dev_box(dev_box, url):
    with pytest.raises(ExternalMcpError) as caught:
        _assert_safe_url(url)
    assert "blocked_internal_address" in str(caught.value)


@pytest.mark.parametrize("url", METADATA_URLS)
def test_the_metadata_endpoint_is_refused_in_production(monkeypatch, url):
    monkeypatch.setattr(settings, "external_mcp_allow_private", False)
    with pytest.raises(ExternalMcpError):
        _assert_safe_url(url)


def test_the_flag_still_does_the_job_it_exists_for(dev_box):
    """Locking the door must not brick the dogfood workflow it was opened for."""
    _assert_safe_url("http://127.0.0.1:8000/mcp/")   # the box itself
    _assert_safe_url("http://192.168.1.44:9000/mcp") # the server on the desk


def test_without_the_flag_the_laptop_is_off_limits_again(monkeypatch):
    monkeypatch.setattr(settings, "external_mcp_allow_private", False)
    with pytest.raises(ExternalMcpError) as caught:
        _assert_safe_url("http://127.0.0.1:8000/mcp/")
    assert "blocked_internal_address" in str(caught.value)


def test_the_refusal_says_what_the_flag_will_and_will_not_buy(dev_box):
    """The operator who hits this will reach for the flag. Head that off."""
    with pytest.raises(ExternalMcpError) as caught:
        _assert_safe_url("http://169.254.169.254/latest/meta-data/")
    assert "link-local" in str(caught.value)


@pytest.mark.parametrize(
    "url,why",
    [
        ("ftp://example.com/mcp", "only http/https"),
        ("http:///mcp", "missing host"),
    ],
)
def test_the_obvious_nonsense_is_still_refused(url, why):
    with pytest.raises(ExternalMcpError):
        _assert_safe_url(url)
