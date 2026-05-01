// Q6 PB — Next.js middleware: gate /panel/* and /admin/* behind a backend
// session. Unauthenticated visits redirect to /auth/login?next=<path> so
// the user lands on the page they wanted after sign-in. Validation hits
// /auth/me on the backend (proxied through the rewrite chain) so a stale
// cookie also triggers the redirect.
import { NextResponse, type NextRequest } from "next/server";

const PROTECTED_PREFIXES = ["/panel", "/admin"];
const BACKEND_URL = process.env.ABS_BACKEND_URL ?? "http://localhost:8000";

function _isProtected(path: string): boolean {
  return PROTECTED_PREFIXES.some(
    (p) => path === p || path.startsWith(`${p}/`),
  );
}

export async function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname;
  if (!_isProtected(path)) return NextResponse.next();

  const session = req.cookies.get("abs_session");
  if (!session?.value) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }

  // Validate the cookie against the backend. We hit /auth/me directly
  // (not the proxy) so middleware avoids loops and edge-runtime fetch
  // limitations.
  try {
    const res = await fetch(`${BACKEND_URL}/auth/me`, {
      headers: { cookie: `abs_session=${session.value}` },
      cache: "no-store",
    });
    if (!res.ok) {
      const url = req.nextUrl.clone();
      url.pathname = "/login";
      url.searchParams.set("next", path);
      return NextResponse.redirect(url);
    }
  } catch {
    // If the backend is unreachable, allow the request through — the
    // page itself will render the empty state. We don't want to loop
    // when only the backend is down.
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/panel/:path*", "/admin/:path*"],
};
