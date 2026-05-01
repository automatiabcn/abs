"""ABS Stripe Product/Price kurulum yardimcisi.

Kullanim:
  # Test mode (default, guvenli):
  python infra/scripts/setup_stripe_products.py --mode test

  # Live mode (production musteri kabul):
  ABS_STRIPE_SECRET_KEY=sk_live_... python infra/scripts/setup_stripe_products.py --mode live

  # Dry-run (hicbir API cagrisi yapmaz, sadece plan yazar):
  python infra/scripts/setup_stripe_products.py --mode test --dry-run

3 product olusturur (varsa atlar):
  - ABS Self-Host       ($299)   metadata.sku=self-host  metadata.mode=<mode>
  - ABS Team Pack 5     ($1196)  metadata.sku=team-5     metadata.mode=<mode>
  - ABS Team Pack 10    ($2093)  metadata.sku=team-10    metadata.mode=<mode>

Output: Price ID'leri stdout. Cikan satirlari .env'e elle yapistir:
  ABS_PRICE_SELF_HOST=price_...
  ABS_PRICE_TEAM_5=price_...
  ABS_PRICE_TEAM_10=price_...

Idempotent: ayni (metadata.sku, metadata.mode) ile mevcut product+matching
unit_amount price varsa atlar.

Live mode safeguard:
- --mode live verildi VE ABS_STRIPE_SECRET_KEY 'sk_live_' ile baslamiyorsa  -> ABORT (exit 2)
- --mode test verildi VE ABS_STRIPE_SECRET_KEY 'sk_test_' ile baslamiyorsa  -> ABORT (exit 2)
- --dry-run her iki modeda Stripe API cagirmaz.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List


PRODUCTS: List[Dict] = [
    {"name": "ABS Self-Host", "amount": 29900, "metadata_sku": "self-host"},
    {"name": "ABS Team Pack 5", "amount": 119600, "metadata_sku": "team-5"},
    {"name": "ABS Team Pack 10", "amount": 209300, "metadata_sku": "team-10"},
]

# 022 — Annual recurring SKU'lar (--annual flag ile)
ANNUAL_PRODUCTS: List[Dict] = [
    {"name": "ABS Self-Host Annual", "amount": 29999, "metadata_sku": "self-host-annual"},
    {"name": "ABS Team Pack 5 Annual", "amount": 119999, "metadata_sku": "team-5-annual"},
    {"name": "ABS Team Pack 10 Annual", "amount": 209999, "metadata_sku": "team-10-annual"},
]


def _validate_key_mode(api_key: str, mode: str) -> None:
    """Live/test mode ile API key prefix uyumunu kontrol et."""
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
    parser.add_argument(
        "--annual",
        action="store_true",
        help="022 — Annual recurring SKU'ları kur (one-time yerine subscription).",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("ABS_STRIPE_SECRET_KEY", "")
    if not api_key:
        print("ABS_STRIPE_SECRET_KEY env var gerekli", file=sys.stderr)
        return 1

    products_to_create = ANNUAL_PRODUCTS if args.annual else PRODUCTS

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
        if found is not None:
            prices = stripe.Price.list(product=found.id, active=True, limit=10)
            active_price = next(
                (pr for pr in prices.data if pr.unit_amount == spec["amount"]),
                None,
            )
            if active_price is not None:
                print(f"# {spec['metadata_sku']} ({args.mode}) mevcut: {active_price.id}")
                continue
        product = found or stripe.Product.create(
            name=spec["name"],
            metadata={"sku": spec["metadata_sku"], "mode": args.mode},
        )
        price = stripe.Price.create(
            product=product.id,
            currency="usd",
            unit_amount=spec["amount"],
            metadata={"sku": spec["metadata_sku"], "mode": args.mode},
        )
        env_name = _env_name_for(spec["metadata_sku"])
        print(f"{env_name}={price.id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
