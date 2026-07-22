import { NextResponse } from "next/server";

// TODO: replace with your real GitHub App install flow, e.g.
//   return NextResponse.redirect("https://github.com/apps/codecortex/installations/new");
// The backend callback should then redirect to "/?connected=1".
export function GET(request: Request) {
  return NextResponse.redirect(new URL("/?connected=1", request.url));
}
