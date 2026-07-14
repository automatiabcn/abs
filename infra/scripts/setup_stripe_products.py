"""ABS Stripe Product/Price installation helper.

Kullanim:
  # Test mode (default, guvenli):
  python infra/scripts/setup_stripe_products.py --mode test

  # Live mode (production musteri kabul):
  ABS_STRIPE_SECRET_KEY=sk_live_... python infra/scripts/setup_stripe_products.py --mode live

  # Dry-run (hicbir API cagrisi yapmaz, sadece plan yazar):
  python infra/scripts/setup_stripe_products.py --mode test --dry-run

2 product olusturur (varsa atlar) — the product is a monthly subscription:
  - ABS Solo   ($29/month)            metadata.sku=solo  metadata.mode=<mode>
  - ABS Team   ($19/seat/month)       metadata.sku=team  metadata.mode=<mode>

The team price is per seat: checkout sends the seat count as the line item
quantity, so a five-person team is 5 x $19. Both prices are `recurring` — that is
the difference between a subscription and a single charge, and getting it wrong
means a customer who thinks they subscribed is billed once and never again.

Output: Price ID'leri stdout. Cikan satirlari .env'e elle yapistir:
  ABS_PRICE_SOLO=price_...
  ABS_PRICE_TEAM=price_...

Idempotent: with the same (metadata.sku, metadata.mode) as existing product+matching
unit_amount price varsa atlar.

Live mode safeguard:
- --mode live is set and ABS_STRIPE_SECRET_KEY does not start with 'sk_live_' -> ABORT (exit 2)
- --mode test is set and ABS_STRIPE_SECRET_KEY does not start with 'sk_test_' -> ABORT (exit 2)
- --dry-run her iki modeda Stripe API cagirmaz.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List


# `recurring` is what makes a price a subscription. Without it Stripe creates a
# one-time price, and a customer who believes they subscribed is charged once and
# never again — which nobody notices until the month they expect a renewal and it
# does not come.
PRODUCTS: List[Dict] = [
    {"name": "ABS Solo", "amount": 2900, "metadata_sku": "solo",
     "recurring": {"interval": "month"}},
    # Per seat. Checkout multiplies by the seat count (the line item quantity),
    # so this amount is what one person costs for one month.
    {"name": "ABS Team", "amount": 1900, "metadata_sku": "team",
     "recurring": {"interval": "month"}},
]

# There is no annual SKU. The product is sold by the month, and an annual price
# would be a second cadence to keep in step with the licence renewal, the seat
# gate and the pricing page — for a discount nobody has asked for yet.


def _validate_key_mode(api_key: str, mode: str) -> None:
    """Check API key prefix matches the live/test mode."""
    if mode == "live" and not api_key.startswith("sk_live_"):
        print(
            "SECURITY: --mode live but ABS_STRIPE_SECRET_KEY does not start with "
            "'sk_live_'. ABORT.",
            file=sys.stderr,
        )
        sys.exit(2)
    if mode == "test" and not api_key.startswith("sk_test_"):
        print(
            "SECURITY: --mode test but ABS_STRIPE_SECRET_KEY does not start with "
            "'sk_test_'. ABORT.",
            file=sys.stderr,
        )
        sys.exit(2)


def _env_name_for(sku: str) -> str:
    return "ABS_PRICE_" + sku.replace("-", "_").upper()


def _print_dry_run(mode: str, products: List[Dict] = PRODUCTS) -> None:
    print(f"# DRY RUN -- mode={mode} -- hicbir API cagrisi yapilmayacak")
    for spec in products:
        env_name = _env_name_for(spec["metadata_sku"])
        amount_usd = spec["amount"] / 100
        print(
            f"# WOULD-CREATE {spec['name']} ${amount_usd} "
            f"sku={spec['metadata_sku']} mode={mode} -> {env_name}=<price_id>"
        )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ABS Stripe Products bootstrap")
    parser.add_argument("--mode", choices=["test", "live"], default="test")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    api_key = os.environ.get("ABS_STRIPE_SECRET_KEY", "")
    if not api_key:
        print("ABS_STRIPE_SECRET_KEY env var gerekli", file=sys.stderr)
        return 1

    products_to_create = PRODUCTS

    if args.dry_run:
        # Dry-run mode-key uyumunu kontrol etmez; sadece plan yazar (CI/local guvenli).
        _print_dry_run(args.mode, products_to_create)
        return 0

    _validate_key_mode(api_key, args.mode)

    import stripe

    stripe.api_key = api_key

    for spec in products_to_create:
        existing = stripe.Product.list(active=True, limit=100)
        found = next(
            (
                p
                for p in existing.data
                if (getattr(p, "metadata", None) or {}).get("sku")
                == spec["metadata_sku"]
                and (getattr(p, "metadata", None) or {}).get("mode") == args.mode
            ),
            None,
        )
        recurring = spec.get("recurring")
        if found is not None:
            prices = stripe.Price.list(product=found.id, active=True, limit=10)
            # An existing price only counts as this SKU's price if it bills the
            # same way. A one-time price left over from before this fix must not
            # satisfy the check for a subscription price — that is precisely how a
            # renewing plan stays non-renewing through a re-run.
            active_price = next(
                (
                    pr
                    for pr in prices.data
                    if pr.unit_amount == spec["amount"]
                    and bool(getattr(pr, "recurring", None)) == bool(recurring)
                ),
                None,
            )
            if active_price is not None:
                print(f"# {spec['metadata_sku']} ({args.mode}) exists: {active_price.id}")
                continue
        product = found or stripe.Product.create(
            name=spec["name"],
            metadata={"sku": spec["metadata_sku"], "mode": args.mode},
        )
        price_args = dict(
            product=product.id,
            currency="usd",
            unit_amount=spec["amount"],
            metadata={"sku": spec["metadata_sku"], "mode": args.mode},
        )
        if recurring:
            price_args["recurring"] = recurring
        price = stripe.Price.create(**price_args)
        env_name = _env_name_for(spec["metadata_sku"])
        print(f"{env_name}={price.id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
