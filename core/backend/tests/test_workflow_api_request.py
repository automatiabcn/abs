"""Workflow ``api_request`` node — real SSRF-guarded HTTP execution.

Round A of the durable-engine follow-up: api_request used to be recorded as
``skipped``. It now issues a real outbound request, but only after an SSRF
guard clears the (templated) URL. These tests pin the guard's allow/deny arms
and the runner's request/retry/block behaviour with sockets + httpx faked.
"""

import socket

import pytest

import app.workflow_v10.net_guard as net_guard
import app.workflow_v10.runner as runner


# ---- net_guard (SSRF) -------------------------------------------------------

def _fake_getaddrinfo(ip):
    def _inner(host, port, **kw):  # noqa: ANN001
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))]
    return _inner


def test_guard_allows_public_ip(monkeypatch):
    monkeypatch.setattr(net_guard.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    net_guard.assert_safe_url("https://example.com/api")  # no raise


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "169.254.169.254", "10.0.0.5", "192.168.1.1", "::1", "0.0.0.0"],
)
def test_guard_blocks_non_public(monkeypatch, ip):
    monkeypatch.setattr(net_guard.socket, "getaddrinfo", _fake_getaddrinfo(ip))
    with pytest.raises(net_guard.UnsafeUrlError):
        net_guard.assert_safe_url("https://internal.example/")


def test_guard_blocks_non_http_scheme():
    with pytest.raises(net_guard.UnsafeUrlError):
        net_guard.assert_safe_url("file:///etc/passwd")


# ---- runner api_request -----------------------------------------------------

class _FakeResp:
    def __init__(self, text, status=200):  # noqa: ANN001
        self.text = text
        self.status_code = status


class _FakeClient:
    def __init__(self, resp=None, exc=None, calls=None):  # noqa: ANN001
        self._resp = resp
        self._exc = exc
        self._calls = calls if calls is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):  # noqa: ANN001
        return False

    async def request(self, method, url, **kw):  # noqa: ANN001
        self._calls.append((method, url, kw))
        if self._exc is not None:
            raise self._exc
        return self._resp


async def _run_node(node, outputs=None):  # noqa: ANN001
    return await runner._run_node(node, node["kind"], outputs or {}, "demo")


def test_api_request_executes_and_templates(monkeypatch):
    import httpx

    calls: list = []
    monkeypatch.setattr(net_guard.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeClient(resp=_FakeResp("PONG", 200), calls=calls)
    )

    node = {
        "id": "a1",
        "kind": "api_request",
        "config": {"method": "POST", "url": "https://api.example.com/{{n0}}", "prompt": "hi {{n0}}"},
        "timeout_s": 5,
    }
    out = __import__("asyncio").run(_run_node(node, {"n0": {"text": "v1"}}))

    assert out["status_code"] == 200
    assert out["text"] == "PONG"
    # URL + body templated from upstream n0 output.
    assert calls[0][1] == "https://api.example.com/v1"
    assert calls[0][2].get("content") == "hi v1"


def test_api_request_blocks_ssrf(monkeypatch):
    monkeypatch.setattr(net_guard.socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    node = {"id": "a1", "kind": "api_request", "config": {"method": "GET", "url": "http://169.254.169.254/latest/meta-data/"}}
    out = __import__("asyncio").run(_run_node(node))
    assert "error" in out and "unsafe url" in out["error"]


def test_api_request_retries_then_errors(monkeypatch):
    import httpx

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeClient(exc=httpx.ConnectError("down"))
    )
    node = {"id": "a1", "kind": "api_request", "config": {"method": "GET", "url": "https://x.example/"}, "retry_max": 2}
    out = __import__("asyncio").run(_run_node(node))
    assert "error" in out
    assert "3 attempt" in out["error"]  # 1 + retry_max(2)


def test_api_request_no_url_skipped():
    node = {"id": "a1", "kind": "api_request", "config": {"method": "GET", "url": ""}}
    out = __import__("asyncio").run(_run_node(node))
    assert out.get("skipped") == "api_request"
