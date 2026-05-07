/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import { NextResponse } from "next/server";
import Stripe from "stripe";

export const runtime = "nodejs";

type Tier = "self-host" | "maintenance" | "team-5" | "team-10";

const priceIdMap: Record<Tier, string | undefined> = {
  "self-host": process.env.STRIPE_PRICE_ID_SELF_HOST,
  maintenance: process.env.STRIPE_PRICE_ID_MAINTENANCE,
  "team-5": process.env.STRIPE_PRICE_ID_TEAM_5,
  "team-10": process.env.STRIPE_PRICE_ID_TEAM_10,
};

let stripeClient: Stripe | null = null;

function getStripe(): Stripe {
  if (!stripeClient) {
    const secret = process.env.STRIPE_SECRET_KEY;
    if (!secret) {
      throw new Error("STRIPE_SECRET_KEY yapılandırılmamış");
    }
    stripeClient = new Stripe(secret, {
      apiVersion: "2025-02-24.acacia",
      typescript: true,
    });
  }
  return stripeClient;
}

const VALID_TIERS: ReadonlySet<Tier> = new Set([
  "self-host",
  "maintenance",
  "team-5",
  "team-10",
]);

function seatCountForTier(tier: Tier): string {
  if (tier === "team-5") return "5";
  if (tier === "team-10") return "10";
  return "1";
}

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as { tier?: Tier };
    const tier = body.tier;

    if (!tier || !VALID_TIERS.has(tier)) {
      return NextResponse.json({ error: "Geçersiz tier" }, { status: 400 });
    }

    if (!process.env.STRIPE_SECRET_KEY) {
      return NextResponse.json(
        { error: "Stripe henüz yapılandırılmadı" },
        { status: 503 },
      );
    }

    const priceId = priceIdMap[tier];
    if (!priceId) {
      return NextResponse.json(
        { error: `Price ID tanımlı değil: ${tier}` },
        { status: 500 },
      );
    }

    const origin = new URL(req.url).origin;

    const session = await getStripe().checkout.sessions.create({
      mode: "payment",
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${origin}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/`,
      allow_promotion_codes: true,
      billing_address_collection: "auto",
      metadata: {
        tier,
        seat_count: seatCountForTier(tier),
      },
    });

    return NextResponse.json({ url: session.url });
  } catch (error) {
    console.error("Checkout session creation failed:", error);
    return NextResponse.json(
      { error: "Ödeme oturumu oluşturulamadı" },
      { status: 500 },
    );
  }
}
