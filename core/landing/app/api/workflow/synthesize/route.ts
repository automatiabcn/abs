// P1 / S19-close — Next.js proxy → backend /v1/workflows/synthesize
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const cookie = req.headers.get("cookie") ?? "";
  try {
    const upstream = await fetch(`${BACKEND}/v1/workflows/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json", cookie },
      body: JSON.stringify(body),
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (exc) {
    return NextResponse.json(
      { detail: `proxy_error: ${(exc as Error).message}` },
      { status: 502 },
    );
  }
}
