"""Checkout SKU → Price ID + seat_count mapping kontrolleri."""

from __future__ import annotations


def test_sku_self_host_seat_1():
    from app.api.checkout import _SKU_TO_PRICE

    _resolver, seats = _SKU_TO_PRICE["self-host"]
    assert seats == 1


def test_sku_team_5_and_10_seats():
    from app.api.checkout import _SKU_TO_PRICE

    assert _SKU_TO_PRICE["team-5"][1] == 5
    assert _SKU_TO_PRICE["team-10"][1] == 10


def test_setup_stripe_products_script_compiles():
    """Script syntax-check — runtime exec is NOT mandatory, only py_compile."""
    import py_compile
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "infra" / "scripts" / "setup_stripe_products.py"
    assert script.is_file(), f"script bulunamadı: {script}"
    py_compile.compile(str(script), doraise=True)
