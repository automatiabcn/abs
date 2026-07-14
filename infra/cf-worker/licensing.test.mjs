// The licence authority, tested where it now lives.
//
// Run: node --test infra/cf-worker/
//
// These are the rules the money depends on, and two of them are rules about
// *us* failing rather than the customer: a Stripe outage must never be reported
// as a cancelled subscription, and a key we did not sign must never be renewed.

import assert from "node:assert/strict";
import test from "node:test";

import {
  claimsIfOurs,
  handleRenew,
  liveSubscription,
  mintLicense,
  seatsOn,
} from "./licensing.js";

const json = (obj, status = 200) => ({ status, body: obj });

function pem(label, der) {
  const b64 = Buffer.from(der).toString("base64").match(/.{1,64}/g).join("\n");
  return `-----BEGIN ${label}-----\n${b64}\n-----END ${label}-----`;
}

async function makeEnv(overrides = {}) {
  const pair = await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  );
  const store = new Map();
  return {
    ABS_LICENSE_PRIVATE_KEY: pem("PRIVATE KEY", await crypto.subtle.exportKey("pkcs8", pair.privateKey)),
    ABS_LICENSE_PUBLIC_KEY: pem("PUBLIC KEY", await crypto.subtle.exportKey("spki", pair.publicKey)),
    STRIPE_SECRET_KEY: "sk_test_x",
    ABS_LICENSE_KV: {
      _store: store,
      async get(key, type) {
        const raw = store.get(key);
        if (raw === undefined) return null;
        return type === "json" ? JSON.parse(raw) : raw;
      },
      async put(key, value) {
        store.set(key, value);
      },
    },
    ...overrides,
  };
}

const MONTH_END = Math.floor(Date.now() / 1000) + 30 * 86400;

function stripeReturning(subscriptions) {
  return async () => ({
    ok: true,
    status: 200,
    json: async () => ({ data: subscriptions }),
  });
}

const LIVE_SUB = {
  id: "sub_1",
  status: "active",
  current_period_end: MONTH_END,
  items: { data: [{ quantity: 5 }] },
};

const request = (body) => ({ json: async () => body });

test("a key we mint is a key we recognise", async () => {
  const env = await makeEnv();
  const { token, payload } = await mintLicense(env, {
    customerId: "cus_1",
    tier: "team",
    seatCount: 3,
    expiresAt: MONTH_END,
  });

  const claims = await claimsIfOurs(env, token);
  assert.equal(claims.customer_id, "cus_1");
  assert.equal(claims.seat_count, 3);
  assert.equal(claims.jti, payload.jti);
});

test("a key somebody else signed is not renewable", async () => {
  const mine = await makeEnv();
  const theirs = await makeEnv();
  const { token } = await mintLicense(theirs, {
    customerId: "cus_evil",
    tier: "team",
    seatCount: 99,
    expiresAt: MONTH_END,
  });

  assert.equal(await claimsIfOurs(mine, token), null);

  const res = await handleRenew(request({ license_key: token }), mine, json);
  assert.equal(res.status, 401);
});

test("a tampered key is not our key", async () => {
  const env = await makeEnv();
  const { token } = await mintLicense(env, {
    customerId: "cus_1",
    tier: "solo",
    seatCount: 1,
    expiresAt: MONTH_END,
  });
  const [h, b, s] = token.split(".");
  const forged = [h, b.slice(0, -2) + (b.slice(-2) === "AA" ? "AB" : "AA"), s].join(".");

  assert.equal(await claimsIfOurs(env, forged), null);
});

test("a live subscription gets the seats it is paying for", async (t) => {
  const env = await makeEnv();
  globalThis.fetch = stripeReturning([LIVE_SUB]);
  t.after(() => delete globalThis.fetch);

  const { token } = await mintLicense(env, {
    customerId: "cus_1",
    tier: "team",
    seatCount: 3, // last month they had three
    expiresAt: Math.floor(Date.now() / 1000) + 86400,
  });

  const res = await handleRenew(request({ license_key: token }), env, json);

  assert.equal(res.status, 200);
  assert.equal(res.body.seat_count, 5, "seats come off the subscription, not the old key");
  // One period plus the grace window — not a year.
  assert.equal(res.body.expires_at, MONTH_END + 7 * 86400);

  const fresh = await claimsIfOurs(env, res.body.license_key);
  assert.equal(fresh.seat_count, 5);
});

test("a cancelled subscription gets no key, and hears what happens to its data", async (t) => {
  const env = await makeEnv();
  globalThis.fetch = stripeReturning([{ id: "sub_x", status: "canceled" }]);
  t.after(() => delete globalThis.fetch);

  const { token } = await mintLicense(env, {
    customerId: "cus_1",
    tier: "solo",
    seatCount: 1,
    expiresAt: Math.floor(Date.now() / 1000) + 86400,
  });

  const res = await handleRenew(request({ license_key: token }), env, json);

  assert.equal(res.status, 402);
  assert.match(res.body.message, /exported and\s+deleted|exported and deleted/);
});

test("a card that bounced is not a cancelled subscription", async (t) => {
  // Stripe is still retrying. Taking the customer's server away on the first
  // failed retry is a cruel way to find out about an expired card.
  const env = await makeEnv();
  globalThis.fetch = stripeReturning([{ ...LIVE_SUB, status: "past_due" }]);
  t.after(() => delete globalThis.fetch);

  const { token } = await mintLicense(env, {
    customerId: "cus_1",
    tier: "team",
    seatCount: 5,
    expiresAt: Math.floor(Date.now() / 1000) + 86400,
  });

  const res = await handleRenew(request({ license_key: token }), env, json);
  assert.equal(res.status, 200);
});

test("our outage is never reported as their cancellation", async (t) => {
  // The failure that would cost us a paying customer. A 402 tells their server
  // the subscription is over and it stops asking; a 503 tells it to come back.
  const env = await makeEnv();
  globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  t.after(() => delete globalThis.fetch);

  const { token } = await mintLicense(env, {
    customerId: "cus_1",
    tier: "solo",
    seatCount: 1,
    expiresAt: Math.floor(Date.now() / 1000) + 86400,
  });

  const res = await handleRenew(request({ license_key: token }), env, json);
  assert.equal(res.status, 503, "a Stripe outage read as 'you cancelled'");
});

test("a revoked licence does not renew itself from another machine", async (t) => {
  const env = await makeEnv();
  globalThis.fetch = stripeReturning([LIVE_SUB]);
  t.after(() => delete globalThis.fetch);

  const { token, payload } = await mintLicense(env, {
    customerId: "cus_1",
    tier: "solo",
    seatCount: 1,
    expiresAt: Math.floor(Date.now() / 1000) + 86400,
  });
  await env.ABS_LICENSE_KV.put(`revoked:${payload.jti}`, JSON.stringify({ reason: "refund" }));

  const res = await handleRenew(request({ license_key: token }), env, json);
  assert.equal(res.status, 402);
});

test("seats are the sum of what is being billed", () => {
  assert.equal(seatsOn({ items: { data: [{ quantity: 3 }, { quantity: 2 }] } }), 5);
  assert.equal(seatsOn({ items: { data: [] } }), 1);
});

test("only a live subscription counts as live", async (t) => {
  const env = await makeEnv();
  globalThis.fetch = stripeReturning([
    { id: "old", status: "canceled" },
    { id: "new", status: "active", current_period_end: MONTH_END, items: { data: [{ quantity: 1 }] } },
  ]);
  t.after(() => delete globalThis.fetch);

  const sub = await liveSubscription(env, "cus_1");
  assert.equal(sub.id, "new");
});
