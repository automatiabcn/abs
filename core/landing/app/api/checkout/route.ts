/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

import { NextResponse } from "next/server";
import Stripe from "stripe";

export const runtime = "nodejs";

type Tier = "solo" | "team";

// The team plan is priced per seat and starts at three. Below that, Solo costs
// less — selling a two-person "team" would only be selling someone the wrong
// thing.
const MIN_TEAM_SEATS = 3;
const MAX_SEATS = 500;

const priceIdMap: Record<Tier, string | undefined> = {
  solo: process.env.STRIPE_PRICE_ID_SOLO,
  team: process.env.STRIPE_PRICE_ID_TEAM,
};

let stripeClient: Stripe | null = null;

function getStripe(): Stripe {
  if (!stripeClient) {
    const secret = process.env.STRIPE_SECRET_KEY;
    if (!secret) {
      throw new Error("STRIPE_SECRET_KEY is not configured");
    }
    stripeClient = new Stripe(secret, {
      apiVersion: "2025-02-24.acacia",
      typescript: true,
    });
  }
  return stripeClient;
}

const VALID_TIERS: ReadonlySet<Tier> = new Set<Tier>(["solo", "team"]);

/**
 * Seats are money, so the number is settled here and not taken from the browser.
 * Solo is one person by definition; a team is at least three.
 */
function seatsFor(tier: Tier, requested: unknown): number {
  if (tier === "solo") return 1;
  const n = Math.floor(Number(requested));
  if (!Number.isFinite(n)) return MIN_TEAM_SEATS;
  return Math.min(MAX_SEATS, Math.max(MIN_TEAM_SEATS, n));
}

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as { tier?: Tier; seats?: number };
    const tier = body.tier;

    if (!tier || !VALID_TIERS.has(tier)) {
      return NextResponse.json({ error: "Invalid tier" }, { status: 400 });
    }

    if (!process.env.STRIPE_SECRET_KEY) {
      return NextResponse.json(
        { error: "Stripe is not configured yet" },
        { status: 503 },
      );
    }

    const priceId = priceIdMap[tier];
    if (!priceId) {
      return NextResponse.json(
        { error: `Price ID is not defined: ${tier}` },
        { status: 500 },
      );
    }

    const seats = seatsFor(tier, body.seats);
    const origin = new URL(req.url).origin;

    const session = await getStripe().checkout.sessions.create({
      // A subscription, not a purchase. Both prices are recurring, and a
      // recurring price sold in `payment` mode is a charge that never renews —
      // Stripe refuses it, which is the one mercy in that mistake.
      mode: "subscription",
      line_items: [{ price: priceId, quantity: seats }],
      success_url: `${origin}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/pricing`,
      allow_promotion_codes: true,
      billing_address_collection: "auto",
      metadata: {
        tier,
        seat_count: String(seats),
      },
    });

    return NextResponse.json({ url: session.url });
  } catch (error) {
    console.error("Checkout session creation failed:", error);
    return NextResponse.json(
      { error: "Could not create the checkout session" },
      { status: 500 },
    );
  }
}
