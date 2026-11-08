"use client";

import Link from "next/link";
import useSWR from "swr";
import {
  Activity, AlertTriangle, CheckCircle2, CircleHelp, Database,
  RefreshCw, Server, Smartphone, Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { extractAccounts, extractInstances } from "@/lib/appruncloud";

type Account = {
  id: string;
  handle: string;
  platform: string;
  status: string;
  presence: string;
  persona_id?: string | null;
  persona_name?: string | null;
  last_seen_in_inventory?: string | null;
};

type ServerSummary = {
  id: string;
  name: string;
  status: string;
  devices_total?: number;
  devices_alive?: number;
  accounts_online?: number;
  last_sync?: {
    ok?: boolean;
    accounts_found?: number;
    devices_found?: number;
    created_at?: string;
    error?: string | null;
  } | null;
};

const presenceLabel: Record<string, string> = {
  online: "online",
  stale: "desatualizada",
  missing: "sem localização",
  unbound: "sem device",
};

const statusTone: Record<string, string> = {
  online: "text-active",
  active: "text-active",
  stale: "text-amber-300",
  missing: "text-red-300",
  degraded: "text-amber-300",
  offline: "text-red-300",
};

function formatDate(value?: string | null) {
  if (!value) return "sem sincronização";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "data indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short", timeStyle: "short",
  }).format(date);
}

function readField(value: unknown, keys: string[], depth = 0): string {
  if (!value || typeof value !== "object" || depth > 5) return "";
  const record = value as Record<string, unknown>;

  // Procura primeiro o campo semântico solicitado em cada nível. Ao descer
  // wrappers (`data`, `device`, etc.), mantém os mesmos nomes para não
  // confundir `name`/`model` com `status`.
  for (const key of keys) {
    const field = record[key];
    if (typeof field === "string" || typeof field === "number") return String(field);
    if (typeof field === "boolean" && keys.includes("online")) {
      return field ? "online" : "offline";
    }
  }

  for (const field of Object.values(record)) {
    if (field && typeof field === "object") {
      const nested = readField(field, keys, depth + 1);
      if (nested) return nested;
    }
  }
  return "";
}

function readPreferredField(
  record: Record<string, unknown>,
  containers: string[],
  fields: string[],
): string {
  let hasPreferredContainer = false;
  for (const key of containers) {
    const source = record[key];
    if (source === undefined || source === null) continue;
    hasPreferredContainer = true;
    if (typeof source === "string" || typeof source === "number") return String(source);
    const value = readField(source, fields);
    if (value) return value;
  }
  return hasPreferredContainer ? "" : readField(record, fields);
}

function rootField(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
  }
  return "";
}

function ErrorState({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-red-400/20 bg-red-400/5 p-3 text-xs text-red-200">
      <AlertTriangle size={14} /> Não foi possível carregar {label}.
    </div>
  );
}

export default function Overview() {
  const { data: health, error: healthError, isLoading: healthLoading, mutate: reloadHealth } =
    useSWR("/health", api, { refreshInterval: 15_000 });
  const { data: accountData, error: accountsError, isLoading: accountsLoading, mutate: reloadAccounts } =
    useSWR("/v1/accounts?page=1&per_page=8&sort=seen", api, { refreshInterval: 30_000 });
  const { data: overviewData, error: overviewError, isLoading: overviewLoading, mutate: reloadOverview } =
    useSWR("/v1/overview", api, { refreshInterval: 60_000 });
  const { data: serverData, error: serversError, isLoading: serversLoading, mutate: reloadServers } =
    useSWR("/v1/servers", api, { refreshInterval: 30_000 });
  const { data: centralData, error: centralError, isLoading: centralLoading, mutate: reloadCentral } =
    useSWR("/v1/integrations/appruncloud/instances?include_details=true&detail_limit=6", api, { refreshInterval: 60_000 });

  const accounts: Account[] = accountData?.accounts ?? [];
  const servers: ServerSummary[] = serverData?.servers ?? [];
  const accountTotal = overviewData?.accounts_total ?? accountData?.total;
  const personaTotal = overviewData?.personas_total;
  const deviceTotal = servers.reduce((sum, server) => sum + (server.devices_total ?? 0), 0);
  const devicesOnline = servers.reduce((sum, server) => sum + (server.devices_alive ?? 0), 0);
  const accountsOnline = servers.reduce((sum, server) => sum + (server.accounts_online ?? 0), 0);
  const inventorySynced = servers.filter((server) => server.last_sync?.ok).length;
  const refreshing = healthLoading || accountsLoading || overviewLoading || serversLoading || centralLoading;
  const centralInstances = extractInstances(centralData);
  const centralStatusCode = centralError instanceof Error
    ? centralError.message.match(/\b(\d{3})\b/)?.[1]
    : undefined;
  const centralErrorLabel = centralStatusCode === "503"
    ? "Consulta não configurada. Confira a chave e o ID da organização no backend."
    : centralStatusCode === "401" || centralStatusCode === "403"
      ? "A AppRunCloud recusou a credencial ou o acesso à organização."
      : centralStatusCode === "502"
        ? "A AppRunCloud não respondeu à consulta. Tente atualizar em instantes."
        : "Não foi possível consultar a AppRunCloud. Confira a conexão e tente novamente.";

  async function refresh() {
    await Promise.all([
      reloadHealth(), reloadAccounts(), reloadOverview(), reloadServers(), reloadCentral(),
    ]);
  }

  const healthLabel = healthError
    ? "API indisponível"
    : health?.database === "ok"
      ? "API e banco conectados"
      : health?.status === "degraded"
        ? "API conectada · banco indisponível"
        : healthLoading
          ? "verificando conexão…"
          : "aguardando conexão";

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="label mb-1">Central de operação</p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Visão geral</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Contas, personas e dispositivos em um só lugar. Esta tela consulta o inventário do Olimpo em modo de leitura.
          </p>
        </div>
        <button onClick={refresh} disabled={refreshing} className="btn-ghost">
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          Atualizar
        </button>
      </header>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-surface-border bg-surface-raised/50 px-4 py-3 text-xs">
        <span className={`flex items-center gap-2 ${health?.database === "ok" ? "text-active" : "text-slate-400"}`}>
          {health?.database === "ok" ? <CheckCircle2 size={14} /> : <CircleHelp size={14} />}
          {healthLabel}
        </span>
        <span className="text-slate-600">Ambiente: {health?.env ?? "—"}</span>
        <span className="text-slate-600">Inventários sincronizados: {serversError ? "indisponível" : serversLoading ? "—" : servers.length === 0 ? "nenhum configurado" : `${inventorySynced}/${servers.length}`}</span>
        {health?.dispatch_enabled === false && (
          <span className="rounded border border-amber-300/20 bg-amber-300/5 px-2 py-1 text-amber-200">
            Modo de execução desativado
          </span>
        )}
      </div>

      {health?.kill_switch && (
        <div className="flex items-center gap-2 rounded-lg border border-purple-300/30 bg-purple-300/5 p-3 text-sm text-purple-100">
          <AlertTriangle size={16} /> Interruptor geral acionado.
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Contas cadastradas" value={accountsError ? "—" : accountTotal ?? "—"} detail="registros no banco do Olimpo" icon={Users} href="/contas" />
        <MetricCard label="Personas" value={overviewError ? "—" : personaTotal ?? "—"} detail="identidades cadastradas" icon={Activity} href="/personas" />
        <MetricCard label="Dispositivos online"
          value={serversError || serversLoading || servers.length === 0 ? "—" : `${devicesOnline} / ${deviceTotal}`}
          detail={servers.length === 0 && !serversError && !serversLoading ? "nenhum servidor configurado" : "online / inventariados"}
          icon={Smartphone} href="/servidores" />
        <MetricCard label="Contas em dispositivos"
          value={serversError || serversLoading || servers.length === 0 ? "—" : accountsOnline}
          detail={servers.length === 0 && !serversError && !serversLoading ? "sem inventário de dispositivos" : "logins reportados no último inventário"}
          icon={Database} href="/servidores" />
      </section>

      <div className="grid gap-5 xl:grid-cols-[1.45fr_1fr]">
        <section className="card overflow-hidden !p-0">
          <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-200">Contas recentes · com e sem persona</h2>
              <p className="mt-0.5 text-xs text-slate-500">Inclui contas vinculadas e não vinculadas a uma persona.</p>
            </div>
            <Link href="/contas" className="text-xs text-info hover:underline">Ver todas</Link>
          </div>
          {accountsError ? <div className="p-4"><ErrorState label="as contas" /></div> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[570px] text-left text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-slate-600">
                  <tr>
                    <th className="px-4 py-2 font-medium">Conta</th>
                    <th className="px-3 py-2 font-medium">Persona</th>
                    <th className="px-3 py-2 font-medium">Presença</th>
                    <th className="px-4 py-2 text-right font-medium">Atualizada</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((account) => (
                    <tr key={account.id} className="border-t border-surface-border/70 hover:bg-surface-raised/50">
                      <td className="px-4 py-2.5">
                        <Link href={`/contas/${account.id}`} className="font-medium text-slate-200 hover:text-info">
                          {account.handle}
                        </Link>
                        <div className="mt-0.5 text-[10px] text-slate-600">{account.platform} · {account.status}</div>
                      </td>
                      <td className="px-3 py-2.5 text-xs text-slate-400">
                        {account.persona_id ? <Link href={`/personas/${account.persona_id}`} className="hover:text-info">{account.persona_name ?? "Persona vinculada"}</Link> : <span className="text-slate-600">sem persona</span>}
                      </td>
                      <td className={`px-3 py-2.5 text-xs ${statusTone[account.presence] ?? "text-slate-400"}`}>
                        {presenceLabel[account.presence] ?? account.presence ?? "desconhecida"}
                      </td>
                      <td className="px-4 py-2.5 text-right text-[10px] text-slate-500">
                        {formatDate(account.last_seen_in_inventory)}
                      </td>
                    </tr>
                  ))}
                  {!accountsLoading && accounts.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-8 text-center text-xs text-slate-500">Nenhuma conta no inventário ainda.</td></tr>
                  )}
                  {accountsLoading && accounts.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-8 text-center text-xs text-slate-500">Carregando contas…</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-200">Servidores e dispositivos</h2>
              <p className="mt-0.5 text-xs text-slate-500">Resumo das fontes de inventário configuradas</p>
            </div>
            <Link href="/integracoes/appruncloud" aria-label="Abrir inventário AppRunCloud"
              className="rounded p-1 text-slate-500 hover:bg-surface-border/40 hover:text-info">
              <Server size={16} />
            </Link>
          </div>
          <div className="rounded-md border border-surface-border bg-surface/50 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-slate-300">Central AppRunCloud</span>
              {centralLoading ? (
                <span className="text-[10px] text-slate-500">consultando…</span>
              ) : centralError ? (
                <span className="text-[10px] text-amber-200">sem conexão de leitura</span>
              ) : (
                <span className="text-[10px] text-active">conectada</span>
              )}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {centralError
                ? centralErrorLabel
                : centralLoading
                  ? "Lendo instâncias e contas conectadas."
                  : centralInstances
                    ? `${centralInstances.length} instâncias retornadas pela central.`
                    : "A consulta respondeu; o formato da lista ainda não foi reconhecido."}
            </div>
            <Link href="/integracoes/appruncloud"
              className="mt-2 inline-flex text-[10px] text-info hover:underline">
              Abrir inventário completo de leitura
            </Link>
            {!centralError && centralInstances && centralInstances.length > 0 && (
              <div className="mt-3 space-y-2 border-t border-surface-border pt-3">
                {centralInstances.slice(0, 6).map((instance: Record<string, unknown>, index: number) => {
                  const instanceId = rootField(instance, ["id", "instance_id", "uuid"]);
                  const loggedAccounts = extractAccounts(
                    instance.instagram_accounts_detail ?? instance.instagram_accounts ?? instance.accounts,
                  );
                  const account = loggedAccounts !== null
                    ? `${loggedAccounts.length} conta${loggedAccounts.length === 1 ? "" : "s"} logada${loggedAccounts.length === 1 ? "" : "s"}`
                    : readPreferredField(
                    instance,
                    ["account_detail", "account", "logged_account", "instagram", "user"],
                    ["username", "handle", "name", "account"],
                  );
                  const device = readPreferredField(
                    instance,
                    ["device_detail", "device", "android"],
                    ["device_name", "model", "name", "label"],
                  );
                  const state = readPreferredField(
                    instance,
                    ["device_detail", "device", "android"],
                    ["status", "state", "connection_status", "online"],
                  );
                  const detailIssue = Boolean(
                    instance.account_detail_error ||
                    instance.instagram_accounts_error ||
                    instance.device_detail_error
                  );
                  return (
                    <div key={instanceId || index} className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[10px]">
                      <span className="truncate text-slate-300">{account || "Conta não informada"}</span>
                      <span className={detailIssue ? "text-amber-200" : "text-slate-500"}>{state || (detailIssue ? "detalhe indisponível" : "estado não informado")}</span>
                      <span className="col-span-2 truncate text-slate-600">{device || "Dispositivo sem identificação"}{instanceId ? " · " + instanceId : ""}</span>
                    </div>
                  );
                })}
                {centralInstances.length > 6 && (
                  <p className="pt-1 text-[10px] text-slate-600">Exibindo 6 de {centralInstances.length} instâncias.</p>
                )}
              </div>
            )}
          </div>
          {serversError ? <ErrorState label="os servidores" /> : servers.map((server) => (
            <Link key={server.id} href={`/servidores/${server.id}`} className="block rounded-md border border-surface-border bg-surface/50 p-3 transition-colors hover:border-info/30">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate text-sm font-medium text-slate-200">{server.name}</span>
                <span className={`shrink-0 text-[10px] ${statusTone[server.status] ?? "text-slate-500"}`}>● {server.status ?? "sem estado"}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                <span>{server.devices_alive ?? 0}/{server.devices_total ?? 0} dispositivos online</span>
                <span>{server.accounts_online ?? 0} contas conectadas</span>
              </div>
              <div className="mt-2 border-t border-surface-border pt-2 text-[10px] text-slate-600">
                Última consulta: {formatDate(server.last_sync?.created_at)}
                {server.last_sync?.ok === false && <span className="ml-2 text-red-300">consulta com erro</span>}
              </div>
            </Link>
          ))}
          {!serversLoading && !serversError && servers.length === 0 && (
            <div className="rounded-md border border-dashed border-surface-border p-5 text-center text-xs text-slate-500">
              Nenhum servidor configurado. O inventário aparecerá aqui após a configuração.
            </div>
          )}
          {serversLoading && servers.length === 0 && <p className="py-5 text-center text-xs text-slate-500">Carregando servidores…</p>}
        </section>
      </div>

      {(healthError || accountsError || overviewError || serversError) && (
        <p role="status" className="text-xs text-amber-200/80">
          Alguns dados do Olimpo não carregaram. Confira a conexão da API ou do banco e atualize a tela.
        </p>
      )}
    </div>
  );
}

function MetricCard({ label, value, detail, icon: Icon, href }: {
  label: string;
  value: string | number;
  detail: string;
  icon: typeof Users;
  href: string;
}) {
  return (
    <Link href={href} className="card block transition-colors hover:border-info/30">
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        <Icon size={15} className="text-slate-600" strokeWidth={1.75} />
      </div>
      <div className="mt-3 metric">{value}</div>
      <div className="mt-1 text-[11px] text-slate-500">{detail}</div>
    </Link>
  );
}
