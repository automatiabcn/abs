// Brief 4 R1 — landing service liveness probe used by Docker
// HEALTHCHECK + the compose service `landing` healthcheck. Static JSON,
// no DB / backend dependency so the probe stays green even when the
// FastAPI service is restarting.

export const runtime = "nodejs";
export const dynamic = "force-static";

export async function GET() {
  return Response.json({
    status: "ok",
    service: "abs-landing",
    ts: new Date().toISOString(),
  });
}
