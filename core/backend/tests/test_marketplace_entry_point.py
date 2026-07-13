"""Marketplace install — real entry_point image resolution.

Q7 hardcoded the launched image to the local ``abs-plugin-stub:<id>``, so a
plugin's real descriptor ``entry_point`` (e.g. ghcr.io/abs-plugins/...) was
never used. ``_resolve_image`` now prefers the real image when it is present
or pullable and degrades to the stub otherwise — these tests pin both arms
plus the no-entry_point default, using a fake docker client (no daemon).
"""

import app.marketplace.sandbox as sandbox_mod


class _FakeImages:
    def __init__(self, *, has=(), pullable=()):  # noqa: ANN001
        self._has = set(has)
        self._pullable = set(pullable)
        self.pulled: list[str] = []

    def get(self, ref):  # noqa: ANN001
        if ref in self._has:
            return object()
        raise Exception("ImageNotFound")

    def pull(self, ref):  # noqa: ANN001
        if ref in self._pullable:
            self.pulled.append(ref)
            return object()
        raise Exception("pull failed: manifest unknown")


class _FakeClient:
    def __init__(self, images):  # noqa: ANN001
        self.images = images


def _sandbox(images):
    s = sandbox_mod.PluginSandbox.__new__(sandbox_mod.PluginSandbox)
    s.client = _FakeClient(images)
    return s


def test_uses_entry_point_when_image_present_locally():
    ref = "ghcr.io/abs-plugins/slack-thread-rag:1.0.0"
    s = _sandbox(_FakeImages(has=(ref,)))
    assert s._resolve_image("slack-thread-rag", ref) == ref


def test_pulls_entry_point_when_missing_but_pullable():
    ref = "ghcr.io/abs-plugins/notion-sync:1.0.0"
    imgs = _FakeImages(pullable=(ref,))
    s = _sandbox(imgs)
    assert s._resolve_image("notion-sync", ref) == ref
    assert imgs.pulled == [ref]


def test_an_unpullable_image_is_a_failed_install_not_a_busybox():
    """It used to start a local busybox stub and report `status: "running"`.

    So an operator installed a plugin, saw it come up green, and had a container
    that does nothing sitting where the plugin should be — and the signed image the
    cosign check had verified was never pulled at all. A plugin whose image cannot
    be fetched is not installed."""
    import pytest

    from app.marketplace.sandbox import PluginImageUnavailable

    ref = "ghcr.io/abs-plugins/does-not-exist:9.9.9"
    s = _sandbox(_FakeImages())  # not present, not pullable

    with pytest.raises(PluginImageUnavailable) as exc:
        s._resolve_image("does-not-exist", ref)
    assert "Nothing was started" in str(exc.value)


def test_a_plugin_with_no_image_to_run_is_refused():
    import pytest

    from app.marketplace.sandbox import PluginImageUnavailable

    s = _sandbox(_FakeImages())
    for empty in (None, ""):
        with pytest.raises(PluginImageUnavailable):
            s._resolve_image("vllm-endpoint", empty)
