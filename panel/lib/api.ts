// O navegador fala com um proxy same-origin do Next. URLs e segredos da API
// ficam no servidor, fora do bundle público do painel.
const BASE = "/api/olimpo";

/** Fetcher do SWR. Caminhos são relativos à API (ex.: "/v1/accounts").
 *  Retorno `any` de propósito: o SWR infere o tipo do fetcher, e um genérico
 *  aqui faria toda chamada virar `{}` no lado de quem consome. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function api(path: string): Promise<any> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
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
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
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

