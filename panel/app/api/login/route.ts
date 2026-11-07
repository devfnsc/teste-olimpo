import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const expectedPassword = process.env.PANEL_ACCESS_PASSWORD;
  const sessionSecret = process.env.PANEL_SESSION_SECRET;
  if (!expectedPassword || !sessionSecret) {
    return NextResponse.json({ detail: "Acesso do painel não configurado." }, { status: 503 });
  }

  let suppliedPassword = "";
  try {
    const body = await request.json();
    suppliedPassword = typeof body.password === "string" ? body.password : "";
  } catch {
    return NextResponse.json({ detail: "Pedido inválido." }, { status: 400 });
  }

  const suppliedHash = createHash("sha256").update(suppliedPassword).digest();
  const expectedHash = createHash("sha256").update(expectedPassword).digest();
  if (!timingSafeEqual(suppliedHash, expectedHash)) {
    return NextResponse.json({ detail: "Senha incorreta." }, { status: 401 });
  }

  const session = createHmac("sha256", sessionSecret).update("olimpo-panel-session").digest("hex");
  const response = NextResponse.json({ ok: true });
  response.cookies.set("olimpo_session", session, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 8 * 60 * 60,
  });
  return response;
}

