"""LICENSE_KEY → ABS_LICENSE_KEY naming sweep.

The 023 settings model already binds via ``env_prefix='ABS_'``, so the
canonical env var is ``ABS_LICENSE_KEY``. For a long time the
30-minute quickstart guide still documented the un-prefixed
``LICENSE_KEY=demo-30min`` form, which pydantic silently ignored —
a customer following the guide would boot in unlicensed/demo mode
without any warning. That gap is closed two ways:

1. The doc is fixed in the same commit (see ``docs/quickstart-30min.md``).
2. The config module promotes a legacy ``LICENSE_KEY`` into
   ``ABS_LICENSE_KEY`` at import time and emits a DeprecationWarning,
   so any customer who refreshes their pinned compose but forgets to
   update an old ``.env`` keeps booting licensed for one release.

These tests exercise ``_promote_legacy_license_key_env`` *directly*
instead of going through ``importlib.reload(app.config)``. The
config module has import-time side effects (instantiates the
``settings`` singleton, runs ``assert_production_safe``, populates
``_DEV_INSECURE_DEFAULTS``); reloading it mid-suite leaves any
module that already did ``from app.config import settings`` holding
a stale reference, which causes a wave of order-dependent failures
in unrelated test files. The shim is a pure function over
``os.environ``, so we test it as one — no module rebinding, no
ripple effect.
"""

from __future__ import annotations

import os
import warnings

from app.config import _promote_legacy_license_key_env


def _scrub_env(monkeypatch) -> None:
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    monkeypatch.delenv("ABS_LICENSE_KEY", raising=False)


def test_legacy_license_key_promoted_with_deprecation_warning(monkeypatch):
    # operator's .env still says LICENSE_KEY=demo-30min (the
    # the older doc shape). The shim must copy that into
    # ABS_LICENSE_KEY so the Settings model picks it up, AND emit a
    # DeprecationWarning visible to the operator's stderr.
    _scrub_env(monkeypatch)
    monkeypatch.setenv("LICENSE_KEY", "demo-30min-legacy")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _promote_legacy_license_key_env()

    assert os.environ.get("ABS_LICENSE_KEY") == "demo-30min-legacy"
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations, "expected DeprecationWarning for legacy LICENSE_KEY env"
    assert "ABS_LICENSE_KEY" in str(deprecations[0].message)


def test_canonical_license_key_wins_over_legacy(monkeypatch):
    # When both env vars are set, the canonical ABS_LICENSE_KEY
    # must win unchanged. The shim is a fallback, never an override.
    _scrub_env(monkeypatch)
    monkeypatch.setenv("LICENSE_KEY", "legacy-should-be-ignored")
    monkeypatch.setenv("ABS_LICENSE_KEY", "canonical-wins")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _promote_legacy_license_key_env()

    assert os.environ.get("ABS_LICENSE_KEY") == "canonical-wins"
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    # No warning when the canonical name is already set — operator is
    # already on the new shape, nothing to nudge.
    assert not deprecations, (
        f"unexpected DeprecationWarning: {[str(w.message) for w in deprecations]}"
    )


def test_no_legacy_no_canonical_is_silent(monkeypatch):
    # Pure absence (e.g. customer running in demo mode) must be
    # silent; an unset env var is not a deprecation event.
    _scrub_env(monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _promote_legacy_license_key_env()

    assert os.environ.get("ABS_LICENSE_KEY") is None
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert not deprecations
