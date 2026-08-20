"""Checkout SKU → Price ID + seat_count mapping kontrolleri."""

from __future__ import annotations


def test_the_one_plan_is_the_one_on_sale():
    """One plan, $5 a month (founder's decision, 2026-08-03).

    This asserted {"solo", "team"} before, and before that it had asserted the
    one-off packs. Each time the model changed, the test had to be told — which
    is the point of keeping it: a SKU that stops being sold must also stop
    being purchasable, and the mapping is what decides that.
    """
    from app.api.checkout import _SKU_TO_PRICE

    assert set(_SKU_TO_PRICE) == {"solo"}, (
        "the Solo/Team split was retired; there is one monthly plan"
    )


def test_setup_stripe_products_script_compiles():
    """Script syntax-check — runtime exec is NOT mandatory, only py_compile."""
    import py_compile
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "infra" / "scripts" / "setup_stripe_products.py"
    assert script.is_file(), f"script bulunamadı: {script}"
    py_compile.compile(str(script), doraise=True)
