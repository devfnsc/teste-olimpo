// O navegador fala com um proxy same-origin do Next. URLs e segredos da API
// ficam no servidor, fora do bundle público do painel.
const BASE = "/api/olimpo";

// Os serviços gratuitos do Render podem dormir após um período sem tráfego.
// Uma única sonda compartilhada acorda a API antes de várias telas consultarem
// endpoints diferentes em paralelo.
let healthRequest: Promise<unknown> | null = null;
let healthFreshUntil = 0;
let healthSnapshot: unknown;

async function requestJson(path: string): Promise<any> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch { /* resposta sem JSON */ }
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ""} — ${path}`);
  }
  return res.json();
}

function apiHealth(): Promise<unknown> {
  if (healthRequest) return healthRequest;
  if (Date.now() < healthFreshUntil) return Promise.resolve(healthSnapshot);

  const current = requestJson("/health").then((health) => {
    healthSnapshot = health;
    healthFreshUntil = Date.now() + 4 * 60_000;
    return health;
  }).finally(() => {
    if (healthRequest === current) healthRequest = null;
  });
  healthRequest = current;
  return current;
}

/** Fetcher do SWR. Caminhos são relativos à API (ex.: "/v1/accounts").
 *  Retorno `any` de propósito: o SWR infere o tipo do fetcher, e um genérico
 *  aqui faria toda chamada virar `{}` no lado de quem consome. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function api(path: string): Promise<any> {
  if (path === "/health") return apiHealth();
  await apiHealth();
  return requestJson(path);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function mutate(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<any> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const payload = await res.json();
      detail = typeof payload?.detail === "string" ? payload.detail : "";
    } catch { /* algumas respostas de proxy não têm JSON */ }
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ` — ${path}`}`);
  }
  if (res.status === 204 || res.status === 205) return null;
  return res.json();
}

/**
 * Stream de eventos (SSE). As telas que precisam de tempo real de verdade
 * — visão geral, fila de aprovação, execução de campanha — assinam aqui.
 */
export function subscribeEvents(onEvent: (e: unknown) => void): () => void {
  const source = new EventSource(`${BASE}/v1/events/stream`);
  source.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch {
      /* linha malformada não derruba o feed */
    }
  };
  return () => source.close();
}

/** URL do arquivo de uma mídia. O conteúdo nunca muda (o nome vem do hash),
 *  então o navegador pode cachear para sempre. */
export function urlDaMidia(assetId: string): string {
  return `${BASE}/v1/media/${assetId}/arquivo`;
}

