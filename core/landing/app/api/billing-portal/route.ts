/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The "Manage subscription" modal (components/ManageModal.tsx) POSTs here to
// send a customer to the Stripe billing portal. The route existed only in the
// modal's imagination before this — the fetch went to a path with no handler,
// which in dev hangs the request and leaves the button stuck on "Opening…"
// forever, and in prod 404s into a misleading "no license for that email".
//
// It mirrors app/api/checkout/route.ts: honest 503 while Stripe is not
// configured (billing is switched on last), a real portal session once it is.

import { NextResponse } from "next/server";
import Stripe from "stripe";

export const runtime = "nodejs";

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

function isEmail(value: unknown): value is string {
  return typeof value === "string" && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value);
}

export async function POST(req: Request) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      customer_email?: string;
    };
    const email = body.customer_email;

    if (!isEmail(email)) {
      return NextResponse.json(
        { error: "Enter the email on your license." },
        { status: 400 },
      );
    }

    // Billing is wired up last (see NEXT_PUBLIC_BILLING_ENABLED / the deferred
    // Stripe activation). Until a key is present, say so plainly — the modal
    // renders this instead of spinning.
    if (!process.env.STRIPE_SECRET_KEY) {
      return NextResponse.json(
        { error: "Billing isn't set up on this server yet." },
        { status: 503 },
      );
    }

    // The portal needs the Stripe customer, which we find by the email on their
    // license. No match → the modal's 404 branch tells them to check the
    // address or buy a license first.
    const customers = await getStripe().customers.list({ email, limit: 1 });
    const customer = customers.data[0];
    if (!customer) {
      return NextResponse.json(
        { error: "No license found for that email." },
        { status: 404 },
      );
    }

    const origin = new URL(req.url).origin;
    const session = await getStripe().billingPortal.sessions.create({
      customer: customer.id,
      return_url: `${origin}/`,
    });

    return NextResponse.json({ portal_url: session.url });
  } catch (error) {
    console.error("Billing portal session creation failed:", error);
    return NextResponse.json(
      { error: "Could not open the billing portal. Try again." },
      { status: 500 },
    );
  }
}
