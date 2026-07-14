# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""IP hardening — hardware fingerprint binding tests.

Coverage (5 tests):
    1. fingerprint stable across calls
    2. fingerprint sensitive to component changes
    3. license with matching machine_fp → valid
    4. license with mismatched machine_fp → 403 license_machine_mismatch
    5. legacy license without machine_fp still verifies (backwards compat)
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.licensing import generate_license, verify_license
from app.licensing import fingerprint as fp_mod


def test_fingerprint_stable_across_calls():
    fp_a = fp_mod.collect_machine_fingerprint()
    fp_b = fp_mod.collect_machine_fingerprint()
    assert fp_a == fp_b
    assert len(fp_a) == 64  # sha256 hex


def test_fingerprint_changes_components(monkeypatch):
    baseline = fp_mod.collect_machine_fingerprint()
    monkeypatch.setattr(fp_mod, "_mac_address", lambda: "deadbeefcafe")
    different = fp_mod.collect_machine_fingerprint()
    assert different != baseline


def test_license_machine_fp_match():
    live_fp = fp_mod.collect_machine_fingerprint()
    token = generate_license(
        "cust_match", tier="team", seat_count=2, valid_days=10, machine_fp=live_fp
    )
    payload = verify_license(token)
    assert payload["machine_fp"] == live_fp
    assert payload["customer_id"] == "cust_match"


def test_license_machine_fp_mismatch():
    bogus_fp = "0" * 64
    token = generate_license(
        "cust_mismatch", tier="team", seat_count=1, valid_days=10, machine_fp=bogus_fp
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_license(token)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "license_machine_mismatch"


def test_license_legacy_no_machine_fp_still_valid():
    token = generate_license(
        "cust_legacy", tier="self-host", seat_count=1, valid_days=10
    )
    payload = verify_license(token)
    assert payload["customer_id"] == "cust_legacy"
    # Legacy tokens MUST NOT carry the field (verify it was stripped).
    assert "machine_fp" not in payload
