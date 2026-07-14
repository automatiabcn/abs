/**
 * Service Worker — panel route cache
 *
 * Strategies (by URL pattern):
 *   /panel/*    (HTML documents) → network-first (3 s timeout → cache)
 *   /panel/rag*                  → stale-while-revalidate (background sync)
 *
 * Excluded (always pass-through):
 *   /v1/*    — chat completions, RAG search, etc. must hit the live backend
 *              so cascade errors are surfaced (contract).
 *   /_next/* — build chunks are versioned by hash, never reused.
 *   /auth/*  — credential surface, must never be cached.
 *   non-GET methods — write paths bypass the cache.
 *
 * Two things this used to get wrong, and each one broke an upgrade:
 *
 * 1. /panel/chat was served **cache-first**, and what gets cached there is an
 *    HTML document that names the JS chunks of the build it came from. Once a
 *    customer had opened the chat page they kept that document forever. Ship a
 *    new release, the chunks it names no longer exist, and the panel dies on load
 *    with "Cannot read properties of undefined (reading 'call')" — or, worse, it
 *    quietly goes on rendering the old UI. Offline drafts never needed the
 *    document cached; they live in IndexedDB. Documents are network-first now,
 *    with the cache as the offline fallback it was meant to be.
 *
 * 2. The cache name was the literal "abs-panel-cache-v1" and nothing ever bumped
 *    it, so the activate handler — which deletes every cache that is not the
 *    current one — never had anything to delete. The name now carries the app
 *    version, passed in at registration as ?v=, so a new release opens a new
 *    cache and the old one is dropped on activate.
 */

const VERSION = new URL(self.location.href).searchParams.get("v") || "dev";
const CACHE_NAME = `abs-panel-cache-${VERSION}`;
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

  if (path.startsWith("/panel/rag")) {
    event.respondWith(staleWhileRevalidate(request));
  } else if (path.startsWith("/panel")) {
    event.respondWith(networkFirst(request));
  }
});

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
