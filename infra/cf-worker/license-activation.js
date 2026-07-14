import { handleIssue, handleRenew } from "./licensing.js";

// Cloudflare Worker — ABS license activation server
// Bindings:
//   ABS_LICENSE_KV — KV namespace 'abs-license-state'
// Endpoints:
//   POST /v1/issue              — mint the first key after a purchase (admin)
//   POST /v1/renew              — mint next month's key (authenticated by the key)
//   POST /v1/activate           — first-boot activation (license + machine_fp)
//   POST /v1/heartbeat          — 24h ping (license still valid?)
//   POST /v1/admin/revoke       — founder admin: kill a license
//   GET  /v1/admin/list-active  — founder admin: list active customers
//   GET  /v1/stripe-event/check — webhook idempotency dedup probe (admin auth)
//   POST /v1/stripe-event/mark  — webhook idempotency state writer (admin auth)
//   GET  /health                — uptime probe

// The verifying key lives in the ABS_LICENSE_PUBLIC_KEY secret, next to the
// private half that signs. A copy used to be pasted here and never read once —
// and it was not even the key the product verifies against, so a third authority
// sat in this file looking authoritative.

// SHA-256 of admin Bearer token (founder keeps the plaintext token offline)
const ADMIN_TOKEN_HASH = "5f9fc4cd9d2b5aff8b0872ebe0678c2895cdb1f46ca80a3accada424b83937a2";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

async function sha256Hex(text) {
  const buf = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

async function checkAdminAuth(req) {
  const auth = req.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  const presented = auth.slice(7).trim();
  const presentedHash = await sha256Hex(presented);
  return presentedHash === ADMIN_TOKEN_HASH;
}

async function handleActivate(req, env) {
  let payload;
  try {
    payload = await req.json();
  } catch {
    return jsonResponse({ valid: false, reason: "invalid_json" }, 400);
  }

  const { jti, machine_fp, build_hash, instance_url } = payload;
  if (!jti || !machine_fp) {
    return jsonResponse({ valid: false, reason: "missing_fields" }, 400);
  }

  // Revoke check
  const revoked = await env.ABS_LICENSE_KV.get(`revoked:${jti}`);
  if (revoked) {
    return jsonResponse({ valid: false, reason: "revoked" });
  }

  const now = Date.now();
  const activationKey = `activation:${jti}:${machine_fp}`;
  const existing = await env.ABS_LICENSE_KV.get(activationKey, { type: "json" });

  const record = {
    jti,
    machine_fp,
    build_hash: build_hash || "unknown",
    instance_url: instance_url || "unknown",
    first_seen: existing?.first_seen || now,
    last_seen: now,
    activation_count: (existing?.activation_count || 0) + 1,
    cf_country: req.cf?.country || "??",
    cf_ip: req.headers.get("CF-Connecting-IP") || "unknown",
  };

  await env.ABS_LICENSE_KV.put(activationKey, JSON.stringify(record), {
    expirationTtl: 90 * 86400,
  });

  // Tamper detection: track build_hash drift per jti
  if (build_hash) {
    const tamperKey = `build_hash:${jti}`;
    const known = await env.ABS_LICENSE_KV.get(tamperKey);
    if (known && known !== build_hash) {
      const alertKey = `tamper_alert:${jti}:${now}`;
      await env.ABS_LICENSE_KV.put(
        alertKey,
        JSON.stringify({ previous: known, current: build_hash, instance_url, machine_fp }),
        { expirationTtl: 365 * 86400 }
      );
    } else if (!known) {
      await env.ABS_LICENSE_KV.put(tamperKey, build_hash, { expirationTtl: 365 * 86400 });
    }
  }

  const watermark = (await sha256Hex(`${jti}:${machine_fp}:automatia-abs-2026`)).slice(0, 16);

  return jsonResponse({
    valid: true,
    watermark,
    expires_at: now + 30 * 86400 * 1000,
    server_time: now,
  });
}

async function handleHeartbeat(req, env) {
  let payload;
  try {
    payload = await req.json();
  } catch {
    return jsonResponse({ valid: false, reason: "invalid_json" }, 400);
  }

  const { jti, machine_fp } = payload;
  if (!jti || !machine_fp) {
    return jsonResponse({ valid: false, reason: "missing_fields" }, 400);
  }

  const revoked = await env.ABS_LICENSE_KV.get(`revoked:${jti}`);
  if (revoked) {
    return jsonResponse({ valid: false, reason: "revoked" });
  }

  const activationKey = `activation:${jti}:${machine_fp}`;
  const existing = await env.ABS_LICENSE_KV.get(activationKey, { type: "json" });
  if (existing) {
    // CF Free Tier KV write budget: 1000/day. Backend heartbeat is 30s
    // heartbeat → 2880 hb/day per customer instance. Writing
    // last_seen on EVERY heartbeat would burn 2.88x the daily write
    // budget per customer. Throttle: only re-write the activation
    // record when the cached last_seen is older than 1 hour. With this
    // throttle one customer is 24 writes/day instead of 2880, so the
    // free-tier budget supports ~40 concurrent customer instances
    // before pushing into paid plan territory. Read counts are
    // unaffected (still 2 reads per heartbeat, well under 100k/day).
    // Revoke propagation is unaffected (revoke is a separate write
    // path on /v1/admin/revoke, and the heartbeat read of revoked:${jti}
    // still fires every cycle).
    const HEARTBEAT_WRITE_THROTTLE_MS = 60 * 60 * 1000; // 1h
    const lastSeenAge = Date.now() - (existing.last_seen || 0);
    if (lastSeenAge >= HEARTBEAT_WRITE_THROTTLE_MS) {
      existing.last_seen = Date.now();
      existing.heartbeat_count = (existing.heartbeat_count || 0) + 1;
      await env.ABS_LICENSE_KV.put(activationKey, JSON.stringify(existing), {
        expirationTtl: 90 * 86400,
      });
    }
  }

  return jsonResponse({ valid: true, server_time: Date.now() });
}

async function handleAdminRevoke(req, env) {
  if (!(await checkAdminAuth(req))) {
    return jsonResponse({ error: "unauthorized" }, 401);
  }
  let body;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }
  const { jti, reason } = body;
  if (!jti) return jsonResponse({ error: "jti_required" }, 400);

  await env.ABS_LICENSE_KV.put(
    `revoked:${jti}`,
    JSON.stringify({ revoked_at: Date.now(), reason: reason || "founder_action" }),
    { expirationTtl: 5 * 365 * 86400 }
  );
  return jsonResponse({ revoked: jti, server_time: Date.now() });
}

async function handleAdminList(req, env) {
  if (!(await checkAdminAuth(req))) {
    return jsonResponse({ error: "unauthorized" }, 401);
  }
  const list = await env.ABS_LICENSE_KV.list({ prefix: "activation:" });
  const records = await Promise.all(
    list.keys.map(async (k) => {
      const rec = await env.ABS_LICENSE_KV.get(k.name, { type: "json" });
      if (!rec) return null;
      const revoked = await env.ABS_LICENSE_KV.get(`revoked:${rec.jti}`);
      if (revoked) return null;
      return rec;
    })
  );
  const active = records.filter(Boolean);
  return jsonResponse({ count: active.length, records: active });
}

// Stripe webhook idempotency store. Key = `stripe_event:<event_id>`, TTL 30d
// (Stripe retry window 3d, 30d gives ample margin). Reuses admin Bearer auth.
async function handleStripeEventCheck(req, env) {
  if (!(await checkAdminAuth(req))) {
    return jsonResponse({ error: "unauthorized" }, 401);
  }
  const url = new URL(req.url);
  const eventId = url.searchParams.get("event_id");
  if (!eventId) {
    return jsonResponse({ error: "event_id_required" }, 400);
  }
  const rec = await env.ABS_LICENSE_KV.get(`stripe_event:${eventId}`, { type: "json" });
  if (!rec) {
    return jsonResponse({ processed: false, exists: false });
  }
  return jsonResponse({
    processed: rec.status === "processed",
    exists: true,
    status: rec.status,
    event_type: rec.event_type,
    received_at: rec.received_at,
    processed_at: rec.processed_at || null,
    error: rec.error || null,
  });
}

async function handleStripeEventMark(req, env) {
  if (!(await checkAdminAuth(req))) {
    return jsonResponse({ error: "unauthorized" }, 401);
  }
  let body;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }
  const { event_id, event_type, status, error } = body;
  if (!event_id || !status) {
    return jsonResponse({ error: "event_id_and_status_required" }, 400);
  }
  if (!["received", "processed", "failed"].includes(status)) {
    return jsonResponse({ error: "invalid_status" }, 400);
  }

  const key = `stripe_event:${event_id}`;
  const existing = await env.ABS_LICENSE_KV.get(key, { type: "json" });
  const now = Date.now();
  const record = {
    event_id,
    event_type: event_type || existing?.event_type || "unknown",
    received_at: existing?.received_at || now,
    status,
    processed_at: status === "processed" ? now : existing?.processed_at || null,
    error: error || null,
  };
  await env.ABS_LICENSE_KV.put(key, JSON.stringify(record), {
    expirationTtl: 30 * 86400,
  });
  return jsonResponse({ ok: true, event_id, status, server_time: now });
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(req.url);

    if (url.pathname === "/health") {
      return jsonResponse({ status: "ok", server_time: Date.now() });
    }
    if (url.pathname === "/v1/activate" && req.method === "POST") {
      return handleActivate(req, env);
    }
    if (url.pathname === "/v1/heartbeat" && req.method === "POST") {
      return handleHeartbeat(req, env);
    }
    // A purchase, and the month after it. Minting lives in licensing.js — this
    // Worker is the only place a licence is signed, because it is already the only
    // place one is revoked, and a rule with two homes always ends up with two
    // answers.
    if (url.pathname === "/v1/issue" && req.method === "POST") {
      if (!(await checkAdminAuth(req))) {
        return jsonResponse({ error: "unauthorized" }, 401);
      }
      return handleIssue(req, env, jsonResponse);
    }
    if (url.pathname === "/v1/renew" && req.method === "POST") {
      // No admin token: the caller is the customer's own server, and it proves
      // who it is by presenting a licence we signed.
      return handleRenew(req, env, jsonResponse);
    }
    if (url.pathname === "/v1/admin/revoke" && req.method === "POST") {
      return handleAdminRevoke(req, env);
    }
    if (url.pathname === "/v1/admin/list-active" && req.method === "GET") {
      return handleAdminList(req, env);
    }
    if (url.pathname === "/v1/stripe-event/check" && req.method === "GET") {
      return handleStripeEventCheck(req, env);
    }
    if (url.pathname === "/v1/stripe-event/mark" && req.method === "POST") {
      return handleStripeEventMark(req, env);
    }

    return jsonResponse({ error: "not_found", path: url.pathname }, 404);
  },
};
