"""Sprint 2J FAZ F — LICENSE_KEY → ABS_LICENSE_KEY naming sweep.

The 023 settings model already binds via ``env_prefix='ABS_'``, so the
canonical env var is ``ABS_LICENSE_KEY``. Through Sprint 2I the
30-minute quickstart guide still documented the un-prefixed
``LICENSE_KEY=demo-30min`` form, which pydantic silently ignored —
a customer following the guide would boot in unlicensed/demo mode
without any warning. FAZ F closes that gap two ways:

1. The doc is fixed in the same commit (see ``docs/quickstart-30min.md``).
2. The config module promotes a legacy ``LICENSE_KEY`` into
   ``ABS_LICENSE_KEY`` at import time and emits a DeprecationWarning,
   so any customer who refreshes their pinned compose but forgets to
   update an old ``.env`` keeps booting licensed for one release.

These two tests assert the promotion logic in both directions:
legacy-only → promoted, both present → no override.
"""

from __future__ import annotations

import importlib
import warnings


def _reload_config(monkeypatch, *, legacy: str | None, canonical: str | None) -> None:
    monkeypatch.delenv("LICENSE_KEY", raising=False)
    monkeypatch.delenv("ABS_LICENSE_KEY", raising=False)
    if legacy is not None:
        monkeypatch.setenv("LICENSE_KEY", legacy)
    if canonical is not None:
        monkeypatch.setenv("ABS_LICENSE_KEY", canonical)
    import app.config as cfg
    importlib.reload(cfg)


def test_legacy_license_key_promoted_with_deprecation_warning(monkeypatch):
    # FAZ F — operator's .env still says LICENSE_KEY=demo-30min (the
    # pre-Sprint 2J doc shape). On import the shim must copy that into
    # ABS_LICENSE_KEY so the Settings model picks it up, AND emit a
    # DeprecationWarning visible to the operator's stderr.
    import os
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _reload_config(monkeypatch, legacy="demo-30min-legacy", canonical=None)
        assert os.environ.get("ABS_LICENSE_KEY") == "demo-30min-legacy"
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecations, "expected DeprecationWarning for legacy LICENSE_KEY env"
        assert "ABS_LICENSE_KEY" in str(deprecations[0].message)


def test_canonical_license_key_wins_over_legacy(monkeypatch):
    # FAZ F — when both env vars are set, the canonical ABS_LICENSE_KEY
    # must win unchanged. The shim is a fallback, never an override.
    import os
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _reload_config(
            monkeypatch,
            legacy="legacy-should-be-ignored",
            canonical="canonical-wins",
        )
        assert os.environ.get("ABS_LICENSE_KEY") == "canonical-wins"
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        # No warning when the canonical name is already set — operator
        # is already on the new shape, nothing to nudge.
        assert not deprecations, (
            f"unexpected DeprecationWarning: {[str(w.message) for w in deprecations]}"
        )


def test_no_legacy_no_canonical_is_silent(monkeypatch):
    # FAZ F — pure absence (e.g. customer running in demo mode) must be
    # silent; an unset env var is not a deprecation event.
    import os
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _reload_config(monkeypatch, legacy=None, canonical=None)
        assert os.environ.get("ABS_LICENSE_KEY") is None
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert not deprecations
