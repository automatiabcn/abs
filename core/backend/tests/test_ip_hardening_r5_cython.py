# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""IP hardening — Cython compile setup smoke test.

Coverage (1 test):
    1. setup.py target list includes verifier + fingerprint + quota_monitor.
       A removal of any entry shrinks the IP hardening surface and must
       be a deliberate, signed-off regression.
"""

from __future__ import annotations

from pathlib import Path


def test_cython_setup_targets_present():
    backend_root = Path(__file__).resolve().parents[1]
    setup_module = backend_root / "setup.py"
    text = setup_module.read_text()
    assert "app/licensing/verifier.py" in text
    assert "app/licensing/fingerprint.py" in text
    assert "app/observability/quota_monitor.py" in text
