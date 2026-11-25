import { NextResponse } from "next/server";

// Lightweight route protection: unauthenticated navigation is redirected to /login.
// Real authorization is enforced server-side by the Python API on every request.
export function proxy(request) {
  if (!request.cookies.get("ff_session")) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/functions/:path*", "/workflows/:path*", "/approvals/:path*", "/exceptions/:path*", "/integrations/:path*", "/policies/:path*", "/vendors/:path*", "/audit/:path*", "/builder/:path*", "/analytics/:path*", "/action-center/:path*"],
};
