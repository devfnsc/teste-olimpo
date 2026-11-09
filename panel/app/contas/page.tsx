"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  Search, Plus, ChevronLeft, ChevronRight, Users, Link2, HelpCircle,
  StickyNote, Smartphone, Server, RefreshCw, AlertTriangle, Play, ShieldCheck,
} from "lucide-react";
import { api, mutate } from "@/lib/api";
import { extractAccounts, extractInstances, type AppRunCloudRecord } from "@/lib/appruncloud";
import {
  STATUS, PRESENCA, AUTONOMIA, PLATAFORMA, ARQUETIPO, PAPEL, tempoRelativo,
} from "@/lib/contas";

const ACOES_APPRUNCLOUD = [
  { id: "instagram_whoami", label: "Verificar sessão Instagram", required: "sem parâmetros" },
  { id: "like", label: "Curtir mídia", required: "media", targetKey: "media", targetLabel: "ID ou link da mídia" },
  { id: "save", label: "Salvar mídia", required: "media", targetKey: "media", targetLabel: "ID ou link da mídia" },
  { id: "comment", label: "Comentar em mídia", required: "media, text", targetKey: "media", targetLabel: "ID ou link da mídia" },
  { id: "follow", label: "Seguir perfil", required: "user" },
  { id: "unfollow", label: "Deixar de seguir perfil", required: "user" },
  { id: "direct_send", label: "Enviar mensagem direta", required: "text e exatamente um entre to ou thread" },
  { id: "photo_upload", label: "Publicar foto no feed", required: "file, caption" },
  { id: "video_upload", label: "Publicar vídeo no feed", required: "file, caption" },
  { id: "album_upload", label: "Publicar álbum", required: "files, caption" },
  { id: "reel_upload", label: "Publicar Reel", required: "file, caption" },
  { id: "photo_story", label: "Publicar Story de foto", required: "file" },
  { id: "video_story", label: "Publicar Story de vídeo", required: "file" },
  { id: "account_insights", label: "Consultar métricas da conta", required: "sem parâmetros" },
  { id: "media_insights", label: "Consultar métricas da mídia", required: "media" },
  { id: "media_info", label: "Consultar informações da mídia", required: "media" },
  { id: "user_stories", label: "Consultar Stories do perfil", required: "user" },
  { id: "story_seen", label: "Marcar Story como visto", required: "story_ids" },
  { id: "reels_feed", label: "Consultar lista de Reels", required: "amount (opcional)" },
  { id: "browse_reels", label: "Navegar Reels", required: "count e parâmetros de visualização (opcionais)" },
  { id: "search_and_watch", label: "Buscar e assistir Reels", required: "query e parâmetros de visualização (opcionais)" },
  { id: "device_run", label: "Consultar execução do dispositivo", required: "run_id" },
  { id: "cancel_device_run", label: "Cancelar execução do dispositivo", required: "run_id" },
] as const;

/**
 * Contas.
 *
 * Tabela densa, paginada no servidor, com facetas contadas no banco. Cartões
 * bonitos não sobrevivem a quatro mil contas: o que o operador precisa é
 * varrer, filtrar e agir em lote.
 */
function scalar(value: unknown, keys: string[], depth = 0): string {
  if (!value || typeof value !== "object" || depth > 5) return "";
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = scalar(item, keys, depth + 1);
      if (found) return found;
    }
    return "";
  }
  const record = value as Record<string, unknown>;
  for (const key of keys) {
    const field = record[key];
    if (typeof field === "string" || typeof field === "number") return String(field);
  }
  for (const field of Object.values(record)) {
    const found = scalar(field, keys, depth + 1);
    if (found) return found;
  }
  return "";
}

function normalizedHandle(value: string): string {
  return value.trim().replace(/^@+/, "").toLocaleLowerCase("pt-BR");
}

function handlesFromInstance(instance: AppRunCloudRecord): string[] {
  const primary = scalar(instance.account_detail, ["username", "handle"])
    || scalar(instance.account, ["username", "handle"])
    || scalar(instance.logged_account, ["username", "handle"]);
  if (primary) return [primary];
  const accounts = extractAccounts(
    instance.instagram_accounts_detail ?? instance.instagram_accounts ?? instance.accounts,
  ) ?? [];
  return [...new Set(accounts.map((account) => scalar(account, ["username", "handle"])) .filter(Boolean))];
}

export default function Contas() {
  const [q, setQ] = useState("");
  const [filtros, setFiltros] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [instanciasSelecionadas, setInstanciasSelecionadas] = useState<Set<string>>(new Set());
  const [buscaInstancia, setBuscaInstancia] = useState("");
  const [acaoSelecionada, setAcaoSelecionada] = useState<string>("");
  const [alvoAcao, setAlvoAcao] = useState("");
  const [parametrosJson, setParametrosJson] = useState("{}");
  const [erroPrevia, setErroPrevia] = useState<string | null>(null);
  const [previa, setPrevia] = useState<any>(null);
  const [gerandoPrevia, setGerandoPrevia] = useState(false);
  const [novo, setNovo] = useState(false);

  const query = useMemo(() => {
    const p = new URLSearchParams({ page: String(page), per_page: "50" });
    if (q.trim()) p.set("q", q.trim());
    for (const [k, v] of Object.entries(filtros)) if (v) p.set(k, v);
    return p.toString();
  }, [q, filtros, page]);

  const { data, mutate: reload } = useSWR(`/v1/accounts?${query}`, api, {
    refreshInterval: 30_000, keepPreviousData: true,
  });
  const { data: inventarioData, error: inventarioError, isLoading: inventarioLoading, mutate: reloadInventario } =
    useSWR("/v1/integrations/appruncloud/instances", api, { refreshInterval: 60_000 });
  const { data: vinculosData, isLoading: vinculosLoading } = useSWR(
    "/v1/accounts?page=1&per_page=500", api,
  );

  const contas = data?.accounts ?? [];
  const facets = data?.facets ?? {};
  const inventario = extractInstances(inventarioData) ?? [];
  const acoesSelecionadasMeta = ACOES_APPRUNCLOUD.find((acao) => acao.id === acaoSelecionada);
  const idInstanciaSelecionada = [...instanciasSelecionadas][0];
  const instanciaSelecionada = inventario.find((instance, index) =>
    (scalar(instance, ["id", "instance_id", "uuid"]) || `instância-${index + 1}`) === idInstanciaSelecionada,
  );
  const contaSelecionada = instanciaSelecionada ? handlesFromInstance(instanciaSelecionada).join(", ") : "";
  const instanciasFiltradas = useMemo(() => {
    const busca = buscaInstancia.trim().toLocaleLowerCase("pt-BR");
    if (!busca) return inventario;
    return inventario.filter((instance) => [
      scalar(instance, ["label", "name", "app_name"]),
      scalar(instance, ["id", "instance_id", "uuid"]),
      scalar(instance, ["state", "status", "connection_status"]),
      ...handlesFromInstance(instance),
    ].some((value) => value.toLocaleLowerCase("pt-BR").includes(busca)));
  }, [inventario, buscaInstancia]);
  const contasPorHandle = useMemo(() => {
    const byHandle = new Map<string, Record<string, unknown>>();
    for (const account of vinculosData?.accounts ?? []) {
      const key = normalizedHandle(String(account.handle ?? ""));
      if (key && !byHandle.has(key)) byHandle.set(key, account);
    }
    return byHandle;
  }, [vinculosData]);

  function alternarFiltro(chave: string, valor: string) {
    setFiltros((f) => ({ ...f, [chave]: f[chave] === valor ? "" : valor }));
    setPage(1);
    setSel(new Set());
  }

  async function emLote(action: string, value?: any) {
    await mutate("/v1/accounts/bulk", "POST", { ids: [...sel], action, value });
    setSel(new Set());
    reload();
  }

  function alternarInstancia(id: string, marcada: boolean) {
    setInstanciasSelecionadas((current) => {
      if (acaoSelecionada === "instagram_whoami") {
        const next = new Set(current);
        if (marcada) next.add(id); else next.delete(id);
        return next;
      }
      return marcada ? new Set([id]) : new Set();
    });
    setPrevia(null);
  }

  async function gerarPrevia() {
    setErroPrevia(null);
    const acao = ACOES_APPRUNCLOUD.find((item) => item.id === acaoSelecionada);
    if (!acao) { setErroPrevia("Escolha uma operação para continuar."); return; }
    const instanceIds = [...instanciasSelecionadas];
    if (instanceIds.length === 0) { setErroPrevia("Selecione pelo menos uma conta/instância."); return; }
    if (acao.id !== "instagram_whoami" && instanceIds.length !== 1) { setErroPrevia("Esta operação usa uma conta por prévia. Para selecionar várias, escolha Verificar sessão Instagram."); return; }
    let params: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(parametrosJson);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
      params = parsed as Record<string, unknown>;
    } catch { setErroPrevia("Os parâmetros precisam estar em formato JSON de objeto, por exemplo: { \"media\": \"...\" }"); return; }
    if ("targetKey" in acao) {
      if (!alvoAcao.trim()) { setErroPrevia(`Informe ${acao.targetLabel.toLocaleLowerCase("pt-BR")} para a prévia.`); return; }
      params = { ...params, [acao.targetKey]: alvoAcao.trim() };
    }
    if (instanceIds.some((id) => !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))) {
      setErroPrevia("Uma das instâncias selecionadas não tem um identificador válido.");
      return;
    }
    setGerandoPrevia(true);
    setPrevia(null);
    try {
      const items = await Promise.all(instanceIds.map(async (instanceId) => {
        const result = await mutate("/v1/integrations/appruncloud/actions/preview", "POST", {
          dry_run: true,
          instance_id: instanceId,
          operation: acao.id,
          parameters: params,
        });
        const selectedInstance = inventario.find((instance, index) =>
          (scalar(instance, ["id", "instance_id", "uuid"]) || `instância-${index + 1}`) === instanceId,
        );
        const account = handlesFromInstance(selectedInstance ?? {}).join(", ") || scalar(selectedInstance, ["label", "name", "app_name"]) || instanceId;
        const detalheAlvo = "targetKey" in acao ? `, com destino ${String(params[acao.targetKey])}` : "";
        const humanSummary = acao.id === "instagram_whoami"
          ? `Prévia: consultar o estado da sessão Instagram da conta ${account}. Essa consulta não faz login; esta tela apenas descreve a chamada e não a envia.`
          : `Prévia: ${acao.label} pela conta ${account}${detalheAlvo}. O JSON abaixo descreve a chamada planejada; nenhuma ação foi executada.`;
        return { ...result, human_summary: humanSummary };
      }));
      setPrevia({ items });
    } catch (error) {
      setErroPrevia(error instanceof Error ? error.message : "Não foi possível gerar a prévia.");
    } finally {
      setGerandoPrevia(false);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Contas</h1>
          <p className="mt-1 text-sm text-slate-500">
            Uma conta é um <strong className="text-slate-400">login numa plataforma</strong>.
            A identidade por trás dela é a <Link href="/personas" className="text-info hover:underline">persona</Link>;
            cada persona pode ter até duas contas.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/personas" className="btn-ghost"><Users size={13} /> personas</Link>
          <button onClick={() => setNovo((v) => !v)} className="btn-primary">
            <Plus size={15} /> Nova conta
          </button>
        </div>
      </header>

      <section className="card space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-200"><Server size={14} /> Selecionar conta</h2>
            <p className="mt-1 text-xs text-slate-500">Pesquise por @usuário, nome do dispositivo ou ID. A consulta de sessão aceita várias contas; as outras prévias usam uma por vez.</p>
          </div>
          <button onClick={() => void reloadInventario()} disabled={inventarioLoading} className="btn-ghost">
            <RefreshCw size={12} className={inventarioLoading ? "animate-spin" : ""} /> Atualizar instâncias
          </button>
        </div>
        {inventarioError ? <p role="alert" className="flex items-center gap-2 text-xs text-amber-200"><AlertTriangle size={13} /> Não foi possível carregar as instâncias AppRunCloud.</p>
          : inventarioLoading && inventario.length === 0 ? <p className="text-xs text-slate-500">Carregando instâncias…</p>
          : inventario.length === 0 ? <p className="text-xs text-slate-500">Nenhuma instância retornada.</p>
          : <div className="space-y-2">
            <label className="relative block"><Search size={14} className="absolute left-2.5 top-2.5 text-slate-600" /><input aria-label="Buscar conta ou instância" className="input !mt-0 pl-8" value={buscaInstancia} onChange={(event) => setBuscaInstancia(event.target.value)} placeholder="Buscar por usuário, dispositivo ou ID…" /></label>
            {acaoSelecionada === "instagram_whoami" && <div className="flex gap-2"><button type="button" onClick={() => { setInstanciasSelecionadas(new Set(instanciasFiltradas.map((instance, index) => scalar(instance, ["id", "instance_id", "uuid"]) || `instância-${index + 1}`))); setPrevia(null); }} className="btn-ghost !py-1 text-[10px]">Selecionar resultados da busca</button><button type="button" onClick={() => { setInstanciasSelecionadas(new Set()); setPrevia(null); }} className="btn-ghost !py-1 text-[10px]">Limpar seleção</button></div>}
            <div className="max-h-64 overflow-y-auto rounded-md border border-surface-border">
              {instanciasFiltradas.length === 0 ? <p className="p-3 text-xs text-slate-500">Nenhuma conta corresponde à busca.</p> : instanciasFiltradas.map((instance, index) => {
                const id = scalar(instance, ["id", "instance_id", "uuid"]) || `instância-${index + 1}`;
                const account = handlesFromInstance(instance).join(", ") || "Conta não identificada";
                const device = scalar(instance, ["label", "name", "app_name"]) || "Dispositivo sem nome";
                const state = scalar(instance, ["state", "status", "connection_status"]) || "Estado não informado";
                const selected = instanciasSelecionadas.has(id);
                return <button key={id} type="button" aria-pressed={selected} onClick={() => alternarInstancia(id, !selected)} className={`flex w-full items-center justify-between gap-3 border-b border-surface-border px-3 py-2 text-left last:border-b-0 ${selected ? "bg-info/10" : "hover:bg-surface-raised/60"}`}>
                  <span className="min-w-0"><span className="block truncate text-xs text-slate-200">{account}</span><span className="block truncate text-[10px] text-slate-500">{device} · {state} · {id}</span></span><span className={`shrink-0 rounded border px-2 py-1 text-[10px] ${selected ? "border-info/40 text-info" : "border-surface-border text-slate-500"}`}>{selected ? "Selecionada · remover" : "Selecionar"}</span>
                </button>;
              })}
            </div>
            <p className="text-[10px] text-slate-600">{instanciasFiltradas.length} de {inventario.length} contas/instâncias · {instanciasSelecionadas.size} selecionada(s){instanciasSelecionadas.size === 1 ? `: ${contaSelecionada || "conta não identificada"}` : ""}</p>
          </div>}
        {vinculosLoading && <p className="text-[10px] text-slate-600">Conferindo vínculos com personas…</p>}
      </section>

      <section className="card space-y-3">
        <div className="flex items-start gap-2">
          <ShieldCheck size={16} className="mt-0.5 shrink-0 text-info" />
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Ações AppRunCloud · modo de simulação</h2>
            <p className="mt-1 text-xs text-slate-500">Escolha a operação, a mídia ou destino e a conta. O Olimpo valida e mostra a chamada planejada; a prévia não é encaminhada à AppRunCloud.</p>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr]">
          <label className="block">
            <span className="label">Operação</span>
            <select className="input" value={acaoSelecionada} onChange={(event) => { const nextAction = event.target.value; setAcaoSelecionada(nextAction); if (nextAction !== "instagram_whoami" && instanciasSelecionadas.size > 1) setInstanciasSelecionadas(new Set([[...instanciasSelecionadas][0]])); setPrevia(null); }}>
              <option value="">Escolha uma operação…</option>
              {ACOES_APPRUNCLOUD.map((acao) => <option key={acao.id} value={acao.id}>{acao.label}</option>)}
            </select>
            {acoesSelecionadasMeta && <span className="mt-1 block text-[10px] text-slate-600">Parâmetros esperados: {acoesSelecionadasMeta.required}</span>}
          </label>
          {acoesSelecionadasMeta && "targetKey" in acoesSelecionadasMeta && <label className="block">
            <span className="label">{acoesSelecionadasMeta.targetLabel}</span>
            <input className="input" value={alvoAcao} onChange={(event) => { setAlvoAcao(event.target.value); setPrevia(null); }} placeholder="Cole aqui o ID ou link da mídia" />
          </label>}
          <label className="block">
            <span className="label">Parâmetros de exemplo (JSON)</span>
            <textarea className="input min-h-24 font-mono text-xs" value={parametrosJson} onChange={(event) => { setParametrosJson(event.target.value); setPrevia(null); }} spellCheck={false} />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500">{instanciasSelecionadas.size > 0 ? `${instanciasSelecionadas.size} conta(s) selecionada(s)` : "Selecione uma conta/instância"}</span>
          <button onClick={() => void gerarPrevia()} disabled={!inventario.length || gerandoPrevia} className="btn-primary"><Play size={13} className={gerandoPrevia ? "animate-pulse" : ""} /> {gerandoPrevia ? "Validando prévia…" : "Pré-visualizar chamada"}</button>
          {instanciasSelecionadas.size > 0 && <button onClick={() => { setInstanciasSelecionadas(new Set()); setPrevia(null); }} className="btn-ghost">Limpar seleção</button>}
        </div>
        {erroPrevia && <p role="alert" className="text-xs text-amber-200">{erroPrevia}</p>}
        {previa && <div className="space-y-2 rounded-md border border-info/20 bg-info/5 p-3">
          <p className="text-xs font-medium text-info">Prévia do Olimpo · nenhum pedido enviado à AppRunCloud</p>
          {previa.items.map((item: any) => <div key={item.instance_id} className="space-y-2 rounded border border-surface-border p-2">
            <p className="text-xs text-slate-200">{item.human_summary}</p>
            <p className="text-[10px] text-slate-400">{item.message} · instância {item.instance_id}</p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded border border-surface-border bg-surface/50 p-2 text-[10px] text-slate-400">{JSON.stringify(item.request, null, 2)}</pre>
          </div>)}
        </div>}
      </section>

      {novo && <FormConta onDone={() => { setNovo(false); reload(); }} />}

      {/* ------------------------------------------------------------ busca */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2.5 top-2.5 text-slate-600" />
          <input
            value={q}
            onChange={(e) => { setQ(e.target.value); setPage(1); }}
            placeholder="handle, id da plataforma, telefone ou nome da persona…"
            className="input !mt-0 pl-8"
          />
        </div>
        <span className="shrink-0 text-xs text-slate-500">
          {data?.total ?? 0} conta{data?.total === 1 ? "" : "s"}
        </span>
      </div>

      {/* ----------------------------------------------------------- facetas */}
      <div className="space-y-1.5">
        <Facetas titulo="plataforma" dados={facets.platform} chave="platform"
          ativo={filtros.platform} onClick={alternarFiltro}
          rotulos={(k) => PLATAFORMA[k]?.rotulo ?? k} />
        <Facetas titulo="situação" dados={facets.status} chave="status"
          ativo={filtros.status} onClick={alternarFiltro}
          rotulos={(k) => STATUS[k]?.rotulo ?? k} ajudas={(k) => STATUS[k]?.ajuda} />
        <Facetas titulo="presença" dados={facets.presence} chave="presence"
          ativo={filtros.presence} onClick={alternarFiltro}
          rotulos={(k) => PRESENCA[k]?.rotulo ?? k} ajudas={(k) => PRESENCA[k]?.ajuda} />
        <Facetas titulo="papel" dados={facets.role} chave="role"
          ativo={filtros.role} onClick={alternarFiltro}
          rotulos={(k) => PAPEL[k]?.rotulo ?? k} ajudas={(k) => PAPEL[k]?.ajuda} />
        {facets.unbound > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 shrink-0 text-slate-600">sem persona</span>
            <button
              onClick={() => { setFiltros((f) => ({ ...f, unbound: f.unbound ? "" : "true" })); setPage(1); }}
              className={`rounded border px-2 py-0.5 ${
                filtros.unbound ? "border-warn/50 bg-warn/15 text-amber-200"
                  : "border-surface-border text-slate-400 hover:text-slate-200"
              }`}
            >
              {facets.unbound} sem identidade vinculada
            </button>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------- ações lote */}
      {sel.size > 0 && (
        <BarraDeLote
          quantidade={sel.size}
          onLimpar={() => setSel(new Set())}
          onAcao={emLote}
        />
      )}

      {/* ------------------------------------------------------------ tabela */}
      <div className="overflow-x-auto rounded-lg border border-surface-border">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="bg-surface-raised/60 text-left">
            <tr className="text-xs uppercase tracking-wider text-slate-500">
              <th className="w-8 px-2 py-2">
                <input
                  type="checkbox"
                  checked={contas.length > 0 && sel.size === contas.length}
                  onChange={(e) =>
                    setSel(e.target.checked ? new Set(contas.map((c: any) => c.id)) : new Set())}
                />
              </th>
              <th className="px-2 py-2">conta</th>
              <th className="px-2 py-2">persona</th>
              <th className="px-2 py-2">situação</th>
              <th className="px-2 py-2">presença</th>
              <th className="px-2 py-2 text-right">seguidores</th>
              <th className="px-2 py-2">aut.</th>
              <th className="px-2 py-2">visto</th>
            </tr>
          </thead>
          <tbody>
            {contas.map((c: any) => (
              <Linha
                key={c.id}
                conta={c}
                marcada={sel.has(c.id)}
                onMarcar={(v: boolean) =>
                  setSel((s) => {
                    const n = new Set(s);
                    v ? n.add(c.id) : n.delete(c.id);
                    return n;
                  })}
              />
            ))}
          </tbody>
        </table>

        {contas.length === 0 && (
          <p className="p-6 text-center text-sm text-slate-500">
            Nenhuma conta com esses filtros.
          </p>
        )}
      </div>

      {/* --------------------------------------------------------- paginação */}
      {(data?.pages ?? 1) > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>página {data.page} de {data.pages}</span>
          <div className="flex gap-1">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1} className="btn-ghost">
              <ChevronLeft size={12} /> anterior
            </button>
            <button onClick={() => setPage((p) => p + 1)}
              disabled={page >= data.pages} className="btn-ghost">
              próxima <ChevronRight size={12} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Linha({ conta, marcada, onMarcar }: {
  conta: any; marcada: boolean; onMarcar: (v: boolean) => void;
}) {
  const plat = PLATAFORMA[conta.platform] ?? {
    cor: "border-slate-600 bg-slate-700/30 text-slate-400", rotulo: conta.platform };
  const st = STATUS[conta.status] ?? { rotulo: conta.status, cor: "", ajuda: "" };
  const pr = PRESENCA[conta.presence] ?? { rotulo: conta.presence, cor: "", ajuda: "" };
  const aut = AUTONOMIA[conta.autonomy] ?? { cor: "", nome: conta.autonomy };

  return (
    <tr className={`border-t border-surface-border hover:bg-surface-raised/40 ${
      marcada ? "bg-info/5" : ""}`}>
      <td className="px-2 py-1.5">
        <input type="checkbox" checked={marcada} onChange={(e) => onMarcar(e.target.checked)} />
      </td>
      <td className="px-2 py-1.5">
        <Link href={`/contas/${conta.id}`} className="flex items-center gap-1.5 hover:underline">
          <span className={`rounded border px-1 py-0.5 text-[10px] font-medium ${plat.cor}`}>
            {plat.rotulo}
          </span>
          <span className="truncate text-slate-200">{conta.handle}</span>
          {conta.notes_count > 0 && (
            <StickyNote size={11} className="shrink-0 text-slate-600" />
          )}
        </Link>
        <div className="ml-8 text-[10px] text-slate-600">
          {ARQUETIPO[conta.archetype] ?? conta.archetype}
          {conta.role !== "agent" && ` · ${PAPEL[conta.role]?.rotulo ?? conta.role}`}
        </div>
      </td>
      <td className="px-2 py-1.5">
        {conta.persona_name ? (
          <Link href={`/personas`} className="text-xs text-slate-300 hover:underline">
            {conta.persona_name}
          </Link>
        ) : (
          <span className="flex items-center gap-1 text-xs text-slate-600">
            <Link2 size={10} /> sem persona
          </span>
        )}
      </td>
      <td className="px-2 py-1.5">
        <span title={st.ajuda} className={`rounded border px-1.5 py-0.5 text-[10px] ${st.cor}`}>
          {st.rotulo}
        </span>
      </td>
      <td className="px-2 py-1.5">
        <span title={pr.ajuda} className={`flex items-center gap-1 text-xs ${pr.cor}`}>
          <Smartphone size={10} /> {pr.rotulo}
          {conta.placements > 1 && (
            <span className="text-warn">×{conta.placements}</span>
          )}
        </span>
      </td>
      <td className="px-2 py-1.5 text-right font-mono text-xs tabular-nums text-slate-400">
        {conta.role === "agent" ? conta.followers : "—"}
      </td>
      <td className="px-2 py-1.5">
        <span title={aut.nome} className={`rounded border px-1 py-0.5 text-[10px] ${aut.cor}`}>
          {conta.autonomy}
        </span>
      </td>
      <td className="px-2 py-1.5 text-[10px] text-slate-600">
        {tempoRelativo(conta.last_seen_in_inventory)}
      </td>
    </tr>
  );
}

function Facetas({ titulo, dados, chave, ativo, onClick, rotulos, ajudas }: {
  titulo: string; dados: Record<string, number> | undefined; chave: string;
  ativo?: string; onClick: (k: string, v: string) => void;
  rotulos: (k: string) => string; ajudas?: (k: string) => string | undefined;
}) {
  const entradas = Object.entries(dados ?? {}).sort((a, b) => b[1] - a[1]);
  if (entradas.length === 0) return null;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 shrink-0 text-slate-600">{titulo}</span>
      <div className="flex flex-wrap gap-1">
        {entradas.map(([k, n]) => (
          <button
            key={k}
            title={ajudas?.(k)}
            onClick={() => onClick(chave, k)}
            className={`rounded border px-2 py-0.5 ${
              ativo === k ? "border-info/50 bg-info/15 text-info"
                : "border-surface-border text-slate-400 hover:text-slate-200"
            }`}
          >
            {rotulos(k)} <span className="text-slate-600">{n}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function BarraDeLote({ quantidade, onLimpar, onAcao }: {
  quantidade: number; onLimpar: () => void;
  onAcao: (action: string, value?: any) => Promise<void>;
}) {
  const { data } = useSWR("/v1/personas", api);
  const personas = data?.personas ?? [];

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-info/30 bg-info/5 p-2.5 text-xs">
      <span className="text-info">{quantidade} selecionada{quantidade > 1 ? "s" : ""}</span>

      <select onChange={(e) => e.target.value && onAcao("set_status", e.target.value)}
        defaultValue="" className="input !mt-0 !w-auto !py-1 text-xs">
        <option value="">mudar situação…</option>
        {Object.entries(STATUS).map(([k, v]) => (
          <option key={k} value={k}>{v.rotulo}</option>
        ))}
      </select>

      <select onChange={(e) => e.target.value && onAcao("bind_persona", e.target.value)}
        defaultValue="" className="input !mt-0 !w-auto !py-1 text-xs">
        <option value="">vincular à persona…</option>
        {personas.map((p: any) => {
          const linked = p.accounts?.length ?? 0;
          return <option key={p.id} value={p.id} disabled={linked >= 2}>
            {p.name} ({linked}/2)
          </option>;
        })}
      </select>

      <select onChange={(e) => e.target.value && onAcao("set_role", e.target.value)}
        defaultValue="" className="input !mt-0 !w-auto !py-1 text-xs">
        <option value="">mudar papel…</option>
        {Object.entries(PAPEL).map(([k, v]) => (
          <option key={k} value={k}>{v.rotulo}</option>
        ))}
      </select>

      <button onClick={() => {
        const l = prompt("Rótulos a adicionar (separados por vírgula):");
        if (l) onAcao("add_labels", l.split(",").map((x) => x.trim()).filter(Boolean));
      }} className="btn-ghost">+ rótulo</button>

      <button onClick={onLimpar} className="ml-auto text-slate-500 hover:text-slate-300">
        limpar seleção
      </button>
    </div>
  );
}

function FormConta({ onDone }: { onDone: () => void }) {
  const { data } = useSWR("/v1/personas", api);
  const [f, setF] = useState({
    handle: "", platform: "instagram", role: "agent", persona_id: "", notes: "",
  });
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    setSalvando(true); setErro(null);
    try {
      await mutate("/v1/accounts", "POST", {
        ...f, persona_id: f.persona_id || null, labels: [], profile: {},
      });
      onDone();
    } catch (e) { setErro(String(e)); setSalvando(false); }
  }

  return (
    <div className="card space-y-3">
      <span className="label">Nova conta</span>
      <p className="text-xs text-slate-500">
        Cadastre o login mesmo antes de ele existir num device. O vínculo com o
        container aparece sozinho quando o inventário o encontrar.
      </p>
      <div className="grid gap-3 sm:grid-cols-4">
        <label className="block">
          <span className="label">Plataforma</span>
          <select className="input" value={f.platform}
            onChange={(e) => setF({ ...f, platform: e.target.value })}>
            <option value="instagram">Instagram</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="tiktok">TikTok</option>
          </select>
        </label>
        <label className="block sm:col-span-2">
          <span className="label">
            {f.platform === "whatsapp" ? "Nome do perfil" : "Handle"}
          </span>
          <input className="input" value={f.handle}
            placeholder={f.platform === "whatsapp" ? "FD Producoes" : "@luna.prado"}
            onChange={(e) => setF({ ...f, handle: e.target.value })} />
        </label>
        <label className="block">
          <span className="label">Papel</span>
          <select className="input" value={f.role}
            onChange={(e) => setF({ ...f, role: e.target.value })}>
            {Object.entries(PAPEL).map(([k, v]) => (
              <option key={k} value={k}>{v.rotulo}</option>
            ))}
          </select>
        </label>
        <label className="block sm:col-span-2">
          <span className="label">Persona</span>
          <select className="input" value={f.persona_id}
            onChange={(e) => setF({ ...f, persona_id: e.target.value })}>
            <option value="">— sem identidade vinculada —</option>
            {(data?.personas ?? []).map((p: any) => (
              <option key={p.id} value={p.id} disabled={(p.accounts?.length ?? 0) >= 2}>
                {p.name} ({p.accounts?.length ?? 0}/2)
              </option>
            ))}
          </select>
        </label>
        <label className="block sm:col-span-2">
          <span className="label">Observação</span>
          <input className="input" value={f.notes}
            onChange={(e) => setF({ ...f, notes: e.target.value })} />
        </label>
      </div>
      {erro && <p className="font-mono text-xs text-red-300">{erro}</p>}
      <div className="flex gap-2">
        <button onClick={salvar} disabled={salvando || !f.handle} className="btn-primary">
          {salvando ? "salvando…" : "Cadastrar"}
        </button>
        <button onClick={onDone} className="btn-ghost">Cancelar</button>
      </div>
    </div>
  );
}

