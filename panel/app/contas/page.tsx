"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  Search, Plus, ChevronLeft, ChevronRight, Users, Link2, HelpCircle,
  StickyNote, Smartphone, Server, RefreshCw, AlertTriangle,
} from "lucide-react";
import { api, mutate } from "@/lib/api";
import { extractAccounts, extractInstances, type AppRunCloudRecord } from "@/lib/appruncloud";
import {
  STATUS, PRESENCA, AUTONOMIA, PLATAFORMA, ARQUETIPO, PAPEL, tempoRelativo,
} from "@/lib/contas";

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
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-200"><Server size={14} /> Instâncias AppRunCloud</h2>
            <p className="mt-1 text-xs text-slate-500">Vínculo da instância com uma conta cadastrada e sua persona no Olimpo.</p>
          </div>
          <button onClick={() => void reloadInventario()} disabled={inventarioLoading} className="btn-ghost">
            <RefreshCw size={12} className={inventarioLoading ? "animate-spin" : ""} /> Atualizar instâncias
          </button>
        </div>
        {inventarioError ? <p role="alert" className="flex items-center gap-2 text-xs text-amber-200"><AlertTriangle size={13} /> Não foi possível carregar as instâncias AppRunCloud.</p>
          : inventarioLoading && inventario.length === 0 ? <p className="text-xs text-slate-500">Carregando instâncias…</p>
          : inventario.length === 0 ? <p className="text-xs text-slate-500">Nenhuma instância retornada.</p>
          : <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-slate-600"><tr><th className="py-2 pr-3">Instância</th><th className="py-2 pr-3">Conta identificada</th><th className="py-2 pr-3">Persona</th><th className="py-2">Estado</th></tr></thead>
            <tbody>{inventario.map((instance, index) => {
              const id = scalar(instance, ["id", "instance_id", "uuid"]) || `instância-${index + 1}`;
              const handles = handlesFromInstance(instance);
              const linked = handles.map((handle) => ({ handle, account: contasPorHandle.get(normalizedHandle(handle)) })).filter((item) => item.account);
              const accountLabel = handles.join(", ") || "Conta não identificada";
              const personaLabels = [...new Set(linked.map(({ account }) => String(account?.persona_name ?? (account?.persona_id ? "Persona vinculada" : "Sem persona"))))];
              const personaLabel = handles.length === 0 ? "Não foi possível conferir" : linked.length === 0 ? "Conta sem cadastro no Olimpo" : personaLabels.join(", ");
              const state = scalar(instance, ["state", "status", "connection_status"]) || "Não informado";
              return <tr key={id} className="border-t border-surface-border"><td className="py-2 pr-3"><span className="text-slate-200">{scalar(instance, ["label", "name", "app_name"]) || id}</span><span className="ml-2 font-mono text-[10px] text-slate-600">{id}</span></td><td className="py-2 pr-3 text-slate-300">{accountLabel}</td><td className="py-2 pr-3 text-slate-400">{personaLabel}</td><td className="py-2 text-slate-500">{state}</td></tr>;
            })}</tbody>
          </table></div>}
        {vinculosLoading && <p className="text-[10px] text-slate-600">Conferindo vínculos com personas…</p>}
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
