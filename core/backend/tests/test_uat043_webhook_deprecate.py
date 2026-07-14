"""billing_v10.webhook_idempotent must emit a
DeprecationWarning on import + the DB-backed alternative
(app.api.webhooks.idempotency) is the canonical source of truth."""

from __future__ import annotations

import importlib
import sys
import warnings


def test_legacy_module_emits_deprecation_warning():
    sys.modules.pop("app.billing_v10.webhook_idempotent", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("app.billing_v10.webhook_idempotent")
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations, "expected DeprecationWarning on import"
    msg = str(deprecations[0].message)
    assert "deprecated" in msg.lower()
    assert "app.api.webhooks.idempotency" in msg


def test_canonical_idempotency_module_exposes_claim_event():
    mod = importlib.import_module("app.api.webhooks.idempotency")
    assert hasattr(mod, "claim_event")
