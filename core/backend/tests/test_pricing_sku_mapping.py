"""Checkout SKU → Price ID + seat_count mapping kontrolleri."""

from __future__ import annotations


def test_the_two_plans_are_the_ones_on_sale():
    from app.api.checkout import _SKU_TO_PRICE

    assert set(_SKU_TO_PRICE) == {"solo", "team"}, (
        "the one-off packs were retired; the product is a monthly subscription"
    )


def test_setup_stripe_products_script_compiles():
    """Script syntax-check — runtime exec is NOT mandatory, only py_compile."""
    import py_compile
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "infra" / "scripts" / "setup_stripe_products.py"
    assert script.is_file(), f"script bulunamadı: {script}"
    py_compile.compile(str(script), doraise=True)
