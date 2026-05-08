// Cloudflare Worker — ABS license activation server
// Bindings:
//   ABS_LICENSE_KV — KV namespace 'abs-license-state'
// Endpoints:
//   POST /v1/activate         — first-boot activation (license + machine_fp)
//   POST /v1/heartbeat        — 24h ping (license still valid?)
//   POST /v1/admin/revoke     — founder admin: kill a license
//   GET  /v1/admin/list-active — founder admin: list active customers
//   GET  /health              — uptime probe

const PUBLIC_KEY_PEM = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAl5BvFEnugu006q6sledL
Z11sy/u5CZV9cgsUmFbnahVXVWdgWzcGzGDUP/408OnZi/Psv9vpx1rvyJGED2AR
6PmZvH2luiwNman59prwZr1Ql6T9fqxxp1YezPDL9RwlK3gjSFfee9piSpiamxbE
kguOOxfalzCFgF/vyhWztm6a68wURNVoRbwgT7YaYgz1GdCWl6DfgWz7kRel/+YC
qVVYqy2uXN4ItbLnLPwTmPXTBDLe/2PgiJBLycTJDWD7ees8hW4hDp+aHsiUdMEF
a6NXVbN0Md4fHhik2yyg8FVqZX2kqh6cis/EYEy+fY58Zva3PFTIqKA94aDJ6Sj5
fQIDAQAB
-----END PUBLIC KEY-----`;

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
    existing.last_seen = Date.now();
    existing.heartbeat_count = (existing.heartbeat_count || 0) + 1;
    await env.ABS_LICENSE_KV.put(activationKey, JSON.stringify(existing), {
      expirationTtl: 90 * 86400,
    });
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
    list.keys.map(async (k) => await env.ABS_LICENSE_KV.get(k.name, { type: "json" }))
  );
  return jsonResponse({ count: records.length, records });
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
    if (url.pathname === "/v1/admin/revoke" && req.method === "POST") {
      return handleAdminRevoke(req, env);
    }
    if (url.pathname === "/v1/admin/list-active" && req.method === "GET") {
      return handleAdminList(req, env);
    }

    return jsonResponse({ error: "not_found", path: url.pathname }, 404);
  },
};
