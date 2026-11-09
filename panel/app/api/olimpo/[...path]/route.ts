import { NextRequest, NextResponse } from "next/server";

const ROUTE_PREFIX = "/api/olimpo";
const ACTION_PREVIEW_PATH = "/v1/integrations/appruncloud/actions/preview";
const READ_ONLY_PATHS = [
  /^\/health$/,
  /^\/v1\/overview$/,
  /^\/v1\/accounts(?:\/[^/]+)?$/,
  /^\/v1\/personas(?:\/[^/]+)?$/,
  /^\/v1\/servers(?:\/[^/]+)?$/,
  /^\/v1\/servers\/[^/]+\/(?:devices|discovered)$/,
  /^\/v1\/integrations\/appruncloud\/instances(?:\/[^/]+(?:\/(?:account|device|instagram\/accounts))?)?$/,
  /^\/v1\/media$/,
  /^\/v1\/media\/[^/]+\/arquivo$/,
  /^\/v1\/media\/opcoes$/,
  /^\/v1\/media\/jobs(?:\/[^/]+)?$/,
  /^\/v1\/media\/personas\/[^/]+\/(?:identidade|figurinos)$/,
  /^\/v1\/brands$/,
];

// Escritas administrativas para o painel local. Rotas de automação, geração,
// integração e configuração de servidores não entram nesta lista.
const LOCAL_WRITE_PATHS: Partial<Record<string, RegExp[]>> = {
  POST: [
    /^\/v1\/accounts$/,
    /^\/v1\/accounts\/bulk$/,
    /^\/v1\/accounts\/[^/]+\/notes$/,
    /^\/v1\/personas$/,
  ],
  PATCH: [
    /^\/v1\/accounts\/[^/]+$/,
    /^\/v1\/personas\/[^/]+$/,
  ],
  DELETE: [
    /^\/v1\/accounts\/[^/]+$/,
    /^\/v1\/media\/[^/]+$/,
    /^\/v1\/notes\/[^/]+$/,
  ],
};

function upstreamUrl(request: NextRequest, allowLocalWrite: boolean): URL | null {
  const suffix = request.nextUrl.pathname.slice(ROUTE_PREFIX.length);
  if (!suffix || suffix.includes("\\") || suffix.includes("%")) return null;

  const segments = suffix.split("/");
  if (segments.some((segment) => segment === "." || segment === "..")) return null;
  const readOnly = request.method === "GET" && READ_ONLY_PATHS.some((pattern) => pattern.test(suffix));
  const actionPreview = request.method === "POST" && suffix === ACTION_PREVIEW_PATH;
  if (request.method === "DELETE" && suffix.startsWith("/v1/accounts/") &&
      request.nextUrl.searchParams.get("confirm") !== "apagar-de-verdade") return null;

  const configuredOrigin = process.env.OLIMPO_API_URL;
  if (!configuredOrigin) throw new Error("OLIMPO_API_URL não configurada.");

  const origin = new URL(configuredOrigin);
  if (
    !["http:", "https:"].includes(origin.protocol) ||
    origin.username || origin.password || origin.search || origin.hash || origin.pathname !== "/"
  ) {
    throw new Error("OLIMPO_API_URL deve conter somente a origem HTTP(S) da API.");
  }
  if (process.env.NODE_ENV === "production" && origin.protocol !== "https:") {
    throw new Error("OLIMPO_API_URL precisa usar HTTPS em produção.");
  }

  const isLoopbackOrigin = ["localhost", "127.0.0.1", "::1", "[::1]"].includes(origin.hostname);
  const canWriteLocally = allowLocalWrite && isLoopbackOrigin;
  const localWrite = canWriteLocally && (LOCAL_WRITE_PATHS[request.method] ?? [])
    .some((pattern) => pattern.test(suffix));
  if (!readOnly && !localWrite && !actionPreview) return null;

  const target = new URL(suffix + request.nextUrl.search, origin);
  if (target.origin !== origin.origin) return null;
  return target;
}

async function proxy(request: NextRequest): Promise<NextResponse> {
  try {
    const allowLocalWrite = process.env.NODE_ENV !== "production";
    const isActionPreview = request.method === "POST" &&
      request.nextUrl.pathname === `${ROUTE_PREFIX}${ACTION_PREVIEW_PATH}`;
    if (request.method !== "GET" && !allowLocalWrite && !isActionPreview) {
      return NextResponse.json({ detail: "Este ambiente aceita somente consultas de leitura." }, { status: 405 });
    }
    const target = upstreamUrl(request, allowLocalWrite);
    if (!target) return NextResponse.json({ detail: "Caminho de API inválido." }, { status: 404 });

    const token = process.env.OLIMPO_API_TOKEN;
    if (process.env.NODE_ENV === "production" && !token) {
      return NextResponse.json({ detail: "Token da API não configurado no servidor." }, { status: 503 });
    }

    const headers = new Headers();
    const accept = request.headers.get("accept");
    const contentType = request.headers.get("content-type");
    if (accept) headers.set("accept", accept);
    if (contentType) headers.set("content-type", contentType);
    if (token) headers.set("authorization", `Bearer ${token}`);

    let body: string | undefined;
    if (request.method === "POST" || request.method === "PATCH") {
      if (isActionPreview) {
        const payload = await request.json().catch(() => null);
        if (!payload || typeof payload !== "object" || Array.isArray(payload) ||
            (payload as { dry_run?: boolean }).dry_run !== true ||
            typeof (payload as { operation?: unknown }).operation !== "string" ||
            typeof (payload as { instance_id?: unknown }).instance_id !== "string" ||
            !(payload as { parameters?: unknown }).parameters ||
            typeof (payload as { parameters?: unknown }).parameters !== "object" ||
            Array.isArray((payload as { parameters?: unknown }).parameters)) {
          return NextResponse.json(
            { detail: "A prévia exige uma operação, uma instância, parâmetros JSON e dry_run=true." },
            { status: 400 },
          );
        }
        body = JSON.stringify(payload);
      } else if (request.nextUrl.pathname === `${ROUTE_PREFIX}/v1/accounts/bulk`) {
        const payload = await request.json().catch(() => null);
        const acoesPermitidas = new Set([
          "set_status", "set_role", "bind_persona", "unbind_persona", "add_labels",
        ]);
        if (!payload || typeof payload !== "object" ||
            !acoesPermitidas.has((payload as { action?: string }).action ?? "")) {
          return NextResponse.json(
            { detail: "Ação administrativa em lote inválida ou não permitida." },
            { status: 400 },
          );
        }
        body = JSON.stringify(payload);
      } else {
        body = await request.text();
      }
    }

    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });

    const responseHeaders = new Headers();
    for (const name of ["content-type", "cache-control", "retry-after", "x-request-id"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    const bodyless = [204, 205, 304].includes(upstream.status);
    return new NextResponse(bodyless ? null : upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Falha ao consultar a API.";
    return NextResponse.json({ detail: message }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
