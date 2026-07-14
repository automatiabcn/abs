/**
 * Service Worker — panel route cache
 *
 * Cache name: abs-panel-cache-v1
 *
 * Strategies (by URL pattern):
 *   /panel/chat*                → cache-first   (offline draft persistence)
 *   /panel/dashboard* or /panel → network-first (3 s timeout → cache)
 *   /panel/rag*                 → stale-while-revalidate (background sync)
 *
 * Excluded (always pass-through):
 *   /v1/*    — chat completions, RAG search, etc. must hit live backend
 *              so cascade chaos errors are surfaced (contract).
 *   /_next/* — dev/build chunks are versioned by hash, never reused.
 *   /auth/*  — credential surface, must never be cached.
 *   non-GET methods (POST/PUT/PATCH/DELETE) — write paths bypass cache.
 *
 * Lifecycle:
 *   install  → skipWaiting()
 *   activate → claim clients + delete other versioned caches
 */

const CACHE_NAME = "abs-panel-cache-v1";
const NETWORK_TIMEOUT_MS = 3000;

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  const path = url.pathname;
  if (
    path.startsWith("/v1/") ||
    path.startsWith("/_next/") ||
    path.startsWith("/auth/")
  ) {
    return; // pass through to network
  }

  if (path.startsWith("/panel/chat")) {
    event.respondWith(cacheFirst(request));
  } else if (path.startsWith("/panel/rag")) {
    event.respondWith(staleWhileRevalidate(request));
  } else if (
    path.startsWith("/panel/dashboard") ||
    path === "/panel" ||
    path === "/panel/"
  ) {
    event.respondWith(networkFirst(request));
  }
});

async function cacheFirst(req) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(req);
  if (cached) return cached;
  try {
    const resp = await fetch(req);
    if (resp && resp.ok) cache.put(req, resp.clone());
    return resp;
  } catch (_e) {
    return Response.error();
  }
}

async function networkFirst(req) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), NETWORK_TIMEOUT_MS);
  try {
    const resp = await fetch(req, { signal: controller.signal });
    clearTimeout(timer);
    if (resp && resp.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(req, resp.clone());
    }
    return resp;
  } catch (_e) {
    clearTimeout(timer);
    const cached = await caches.match(req);
    return cached || Response.error();
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(req);
  const fetchPromise = fetch(req)
    .then((resp) => {
      if (resp && resp.ok) cache.put(req, resp.clone());
      return resp;
    })
    .catch(() => null);
  return cached || (await fetchPromise) || Response.error();
}
