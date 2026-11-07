import { NextRequest, NextResponse } from "next/server";

const encoder = new TextEncoder();

async function expectedSession(): Promise<string | null> {
  const secret = process.env.PANEL_SESSION_SECRET;
  if (!secret) return null;
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode("olimpo-panel-session"));
  return Array.from(new Uint8Array(signature), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function sameValue(left: string, right: string): boolean {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

export async function middleware(request: NextRequest) {
  if (process.env.NODE_ENV !== "production") return NextResponse.next();

  const path = request.nextUrl.pathname;
  if (path === "/login" || path === "/api/login" || path.startsWith("/_next/") || path === "/favicon.ico") {
    return NextResponse.next();
  }

  const expected = await expectedSession();
  const actual = request.cookies.get("olimpo_session")?.value ?? "";
  if (expected && sameValue(actual, expected)) return NextResponse.next();

  if (path.startsWith("/api/")) {
    return NextResponse.json({ detail: "Autenticação necessária." }, { status: 401 });
  }
  if (!process.env.PANEL_ACCESS_PASSWORD || !expected) {
    return new NextResponse("Configure PANEL_ACCESS_PASSWORD e PANEL_SESSION_SECRET.", { status: 503 });
  }
  const login = request.nextUrl.clone();
  login.pathname = "/login";
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};

