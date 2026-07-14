// Minting, and the monthly renewal that makes a subscription a subscription.
//
// The licence is an RS256 token the customer's server checks offline, against a
// public key baked into the image. That is what lets the product run on a machine
// with no internet — and it is why a monthly subscription is hard: a key minted
// to last a year has no idea the customer cancelled in month two. Enforcement
// would rest on a revocation call an air-gapped server never receives, which is
// to say on nothing.
//
// So the key is short. It is minted for exactly the billing period the customer
// has paid for, plus the grace window, and their server comes back here a few
// days before it runs out. We ask Stripe — not a table, not a webhook we might
// have missed — whether the subscription is still alive, and mint the next key
// only if it is. Stop paying, and the key expires where it sits.
//
// This is the only place a licence is minted. It used to be a FastAPI endpoint in
// the product itself, which shipped seller code to every customer, could not mint
// (the private key is not theirs), and drifted from the revocation logic that
// already lived here. One rule, one place.

const GRACE_DAYS = 7;

// Live enough to keep working. `past_due` is deliberate: the card bounced, Stripe
// is retrying, and taking someone's server away on the first failed retry is a
// cruel way to find out about an expired card.
const LIVE_STATES = new Set(["active", "trialing", "past_due"]);

const INACTIVE_MESSAGE =
  "Your subscription is no longer active, so no new licence was issued. Chat and " +
  "the agent will pause when the current key runs out. Everything on the server " +
  "stays yours — documents, transcripts and keys can still be read, exported and " +
  "deleted. Subscribe again from the panel, under Settings → Licence.";

function b64urlFromBytes(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlFromString(text) {
  return b64urlFromBytes(new TextEncoder().encode(text));
}

function bytesFromB64url(text) {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

function derFromPem(pem) {
  const body = pem
    .replace(/-----BEGIN [^-]+-----/, "")
    .replace(/-----END [^-]+-----/, "")
    .replace(/\s+/g, "");
  const raw = atob(body);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out.buffer;
}

async function signingKey(env) {
  if (!env.ABS_LICENSE_PRIVATE_KEY) {
    throw new Error("ABS_LICENSE_PRIVATE_KEY is not configured");
  }
  return crypto.subtle.importKey(
    "pkcs8",
    derFromPem(env.ABS_LICENSE_PRIVATE_KEY),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function verifyingKey(env) {
  if (!env.ABS_LICENSE_PUBLIC_KEY) {
    throw new Error("ABS_LICENSE_PUBLIC_KEY is not configured");
  }
  return crypto.subtle.importKey(
    "spki",
    derFromPem(env.ABS_LICENSE_PUBLIC_KEY),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
}

export async function mintLicense(env, { customerId, tier, seatCount, expiresAt }) {
  const now = Math.floor(Date.now() / 1000);
  const jti = crypto.randomUUID().replace(/-/g, "");
  const payload = {
    customer_id: customerId,
    tier,
    seat_count: seatCount,
    iat: now,
    exp: Math.floor(expiresAt),
    jti,
  };

  const head = b64urlFromString(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const body = b64urlFromString(JSON.stringify(payload));
  const signed = `${head}.${body}`;

  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    await signingKey(env),
    new TextEncoder().encode(signed),
  );

  return { token: `${signed}.${b64urlFromBytes(new Uint8Array(signature))}`, payload };
}

/**
 * The claims of a token we actually signed.
 *
 * The signature is checked; the expiry is not, because the key that turns up here
 * is by definition one that is running out — and sometimes one that ran out while
 * the machine was switched off. Returns null when the token is not ours.
 */
export async function claimsIfOurs(env, token) {
  const parts = String(token || "").split(".");
  if (parts.length !== 3) return null;

  try {
    const ok = await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      await verifyingKey(env),
      bytesFromB64url(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
    if (!ok) return null;
    return JSON.parse(new TextDecoder().decode(bytesFromB64url(parts[1])));
  } catch {
    return null;
  }
}

async function stripeGet(env, path) {
  if (!env.STRIPE_SECRET_KEY) throw new Error("STRIPE_SECRET_KEY is not configured");
  const res = await fetch(`https://api.stripe.com/v1/${path}`, {
    headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` },
  });
  if (!res.ok) throw new Error(`stripe ${res.status}`);
  return res.json();
}

/** The customer's live subscription, straight from Stripe. Null when there is none. */
export async function liveSubscription(env, customerId) {
  const data = await stripeGet(
    env,
    `subscriptions?customer=${encodeURIComponent(customerId)}&status=all&limit=10`,
  );
  for (const sub of data.data || []) {
    if (LIVE_STATES.has(sub.status)) return sub;
  }
  return null;
}

/** What the customer is paying for this month — off the subscription, not the old key. */
export function seatsOn(subscription) {
  const items = (subscription.items && subscription.items.data) || [];
  const total = items.reduce((sum, item) => sum + (item.quantity || 0), 0);
  return Math.max(1, total);
}

function validUntil(subscription) {
  const periodEnd = Number(subscription.current_period_end);
  if (!Number.isFinite(periodEnd)) throw new Error("subscription has no period end");
  return periodEnd + GRACE_DAYS * 86400;
}

async function remember(env, payload, { subscriptionId, email }) {
  await env.ABS_LICENSE_KV.put(
    `license:${payload.jti}`,
    JSON.stringify({
      customer_id: payload.customer_id,
      subscription_id: subscriptionId,
      tier: payload.tier,
      seat_count: payload.seat_count,
      email: email || "",
      exp: payload.exp,
      issued_at: payload.iat,
    }),
  );
}

/**
 * POST /v1/issue — a purchase just completed. Mint the first key.
 * Admin-only: this is money, and the caller is our own webhook.
 */
export async function handleIssue(req, env, jsonResponse) {
  let body;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }

  const customerId = String(body.customer_id || "").trim();
  if (!customerId) return jsonResponse({ error: "customer_id required" }, 400);

  let subscription;
  try {
    subscription = await liveSubscription(env, customerId);
  } catch (err) {
    // Ours to fix, and the customer has already paid. Stripe answering slowly
    // must not turn into "you bought it and got nothing".
    return jsonResponse({ error: "billing_unreachable", detail: String(err) }, 503);
  }
  if (!subscription) return jsonResponse({ error: "no_live_subscription" }, 402);

  const { token, payload } = await mintLicense(env, {
    customerId,
    tier: String(body.tier || "solo"),
    seatCount: seatsOn(subscription),
    expiresAt: validUntil(subscription),
  });
  await remember(env, payload, {
    subscriptionId: subscription.id,
    email: body.email,
  });

  return jsonResponse({
    license_key: token,
    jti: payload.jti,
    seat_count: payload.seat_count,
    expires_at: payload.exp,
  });
}

/**
 * POST /v1/renew — a customer's server asking for next month's key.
 *
 * Authenticated by the key itself: only a licence we signed can ask for another
 * one. No admin token, because the caller is the customer's own machine.
 */
export async function handleRenew(req, env, jsonResponse) {
  let body;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }

  const claims = await claimsIfOurs(env, body.license_key);
  if (!claims || !claims.jti) return jsonResponse({ error: "bad_signature" }, 401);

  const revoked = await env.ABS_LICENSE_KV.get(`revoked:${claims.jti}`);
  if (revoked) return jsonResponse({ error: "inactive", message: INACTIVE_MESSAGE }, 402);

  const known = await env.ABS_LICENSE_KV.get(`license:${claims.jti}`, "json");
  // A key we signed but never recorded is a licence issued before this endpoint
  // existed — or by hand. Its customer id is still in the token, and that is
  // enough to ask Stripe the only question that matters.
  const customerId = (known && known.customer_id) || claims.customer_id;
  if (!customerId) return jsonResponse({ error: "inactive", message: INACTIVE_MESSAGE }, 402);

  let subscription;
  try {
    subscription = await liveSubscription(env, customerId);
  } catch (err) {
    // Not their problem. Their server has days of key left and a grace window
    // behind it, and it will simply ask again.
    return jsonResponse({ error: "billing_unreachable", detail: String(err) }, 503);
  }
  if (!subscription) {
    return jsonResponse({ error: "inactive", message: INACTIVE_MESSAGE }, 402);
  }

  const { token, payload } = await mintLicense(env, {
    customerId,
    tier: claims.tier || (known && known.tier) || "solo",
    seatCount: seatsOn(subscription),
    expiresAt: validUntil(subscription),
  });
  await remember(env, payload, {
    subscriptionId: subscription.id,
    email: known && known.email,
  });

  return jsonResponse({
    license_key: token,
    seat_count: payload.seat_count,
    expires_at: payload.exp,
  });
}
