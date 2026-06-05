# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""SSRF guard for workflow ``api_request`` nodes.

A workflow node that issues an outbound HTTP request is attacker-influenced
(the URL may come from upstream node output / templated variables). Without a
guard, a request to ``http://169.254.169.254/`` or ``http://localhost:6333``
would let a tenant pivot into cloud metadata or internal services (qdrant,
neo4j, vault). ``assert_safe_url`` enforces:

  - scheme is http/https only (no file://, gopher://, ...)
  - the host resolves only to public, routable addresses — every resolved IP
    is rejected if it is private / loopback / link-local / reserved /
    multicast / unspecified.

DNS is resolved here (not just parsed) so a hostname that points at a private
IP — the classic DNS-rebinding SSRF — is caught too.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """Raised when a URL is rejected by the SSRF guard."""


_ALLOWED_SCHEMES = frozenset({"http", "https"})


_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def _embedded_ipv4(addr: "ipaddress._BaseAddress"):
    """Extract any IPv4 smuggled inside an IPv6 address (mapped / 6to4 /
    Teredo / NAT64), or None. These forms can route a private v4 through an
    IPv6-looking literal, so the inner address must be validated too."""
    if not isinstance(addr, ipaddress.IPv6Address):
        return None
    if addr.ipv4_mapped:
        return addr.ipv4_mapped
    if addr.sixtofour:
        return addr.sixtofour
    if addr.teredo:
        return addr.teredo[1]  # (server, client) → the client v4
    if addr in _NAT64_PREFIX:
        return ipaddress.ip_address(int(addr) & 0xFFFFFFFF)
    return None


def _ip_is_safe(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # An IPv6 wrapper is only as safe as the IPv4 it may embed.
    inner = _embedded_ipv4(addr)
    if inner is not None and not (inner.is_global and not inner.is_multicast):
        return False
    # is_global is the strict allowlist: everything else (private, loopback,
    # link-local 169.254/fe80, reserved, multicast, unspecified) is rejected.
    return addr.is_global and not addr.is_multicast


def assert_safe_url(url: str) -> None:
    """Raise :class:`UnsafeUrlError` if *url* is not a safe outbound target."""
    if not url or not isinstance(url, str):
        raise UnsafeUrlError("empty url")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("missing host")

    # Resolve every A/AAAA record; reject if ANY is non-public (a host that
    # resolves to both a public and a private IP is still an SSRF vector).
    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"dns resolution failed: {exc}") from exc
    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise UnsafeUrlError("host did not resolve")
    for ip in resolved:
        if not _ip_is_safe(ip):
            raise UnsafeUrlError(f"host resolves to non-public address: {ip}")


__all__ = ["UnsafeUrlError", "assert_safe_url"]
