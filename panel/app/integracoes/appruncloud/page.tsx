"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, RefreshCw, Search, Smartphone } from "lucide-react";
import { api } from "@/lib/api";
import { extractAccounts, extractInstances } from "@/lib/appruncloud";

type RecordValue = Record<string, unknown>;
const PAGE_SIZE = 50;

function asRecord(value: unknown): RecordValue | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as RecordValue
    : null;
}

function scalar(record: RecordValue | null, keys: string[], depth = 0): string {
  if (!record) return "";
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (typeof value === "boolean") return value ? "online" : "offline";
  }
  if (depth >= 5) return "";
  for (const value of Object.values(record)) {
    const nested = scalar(asRecord(value), keys, depth + 1);
    if (nested) return nested;
  }
  return "";
}

function nestedScalar(record: RecordValue, containers: string[], fields: string[]): string {
  for (const key of containers) {
    const value = record[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
    const nested = asRecord(value);
    const result = scalar(nested, fields);
    if (result) return result;
  }
  return scalar(record, fields);
}

function searchableInstance(instance: RecordValue): string {
  const accountRecords = extractAccounts(
    instance.instagram_accounts_detail ?? instance.instagram_accounts ?? instance.accounts,
  ) ?? [];
  return [
    scalar(instance, ["id", "instance_id", "uuid", "name", "label"]),
    nestedScalar(instance, ["account_detail", "account", "logged_account", "instagram", "user"], ["username", "handle", "name", "account"]),
    accountRecords.map((account) => nestedScalar(account, ["account", "user", "instagram"], ["username", "handle", "name", "account"])).join(" "),
    nestedScalar(instance, ["device_detail", "device", "android"], ["device_name", "model", "name", "label"]),
    nestedScalar(instance, ["device_detail", "device", "android"], ["status", "state", "connection_status", "online"]),
  ].join(" ").toLocaleLowerCase("pt-BR");
}

export default function AppRunCloudInventory() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [detailBusyId, setDetailBusyId] = useState<string | null>(null);
  const { data, error, isLoading, mutate } = useSWR(
    "/v1/integrations/appruncloud/instances?include_details=true&detail_limit=6",
    api,
    { refreshInterval: 60_000 },
  );

  const parsedInstances = useMemo(() => extractInstances(data), [data]);
  const instances = parsedInstances ?? [];
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("pt-BR");
    if (!term) return instances;
    return instances.filter((instance) => searchableInstance(instance).includes(term));
  }, [instances, query]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const visibleInstances = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const firstVisible = filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const lastVisible = Math.min(currentPage * PAGE_SIZE, filtered.length);
  const instancesWithDetailErrors = instances.filter((instance) =>
    Boolean(instance.account_detail_error || instance.instagram_accounts_error || instance.device_detail_error),
  ).length;

  const errorMessage = error instanceof Error && error.message.includes("503")
    ? "A conexão de leitura ainda não foi configurada no backend."
    : error instanceof Error && /401|403/.test(error.message)
      ? "A AppRunCloud recusou a credencial ou o acesso à organização."
      : error instanceof Error && error.message.includes("502")
        ? "A AppRunCloud não respondeu à consulta. Tente atualizar em instantes."
      : "Não foi possível consultar as instâncias. Confira a conexão e tente novamente.";

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="label mb-1">Integração · somente leitura</p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Inventário AppRunCloud</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Instâncias e informações retornadas pela central. Esta tela não executa ações nas contas.
          </p>
        </div>
        <button onClick={() => void mutate()} disabled={isLoading} className="btn-ghost">
          <RefreshCw size={13} className={isLoading ? "animate-spin" : ""} /> Atualizar
        </button>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Instâncias retornadas" value={error ? "—" : instances.length} />
        <Metric label="Correspondem à busca" value={error ? "—" : filtered.length} />
        <Metric label="Instâncias com detalhes pendentes" value={error ? "—" : instancesWithDetailErrors} />
        <div className="card flex items-center gap-2 text-sm">
          <span className={`h-2 w-2 rounded-full ${error ? "bg-amber-300" : isLoading ? "bg-slate-500" : "bg-active"}`} />
          <span className="text-slate-300">{error ? "Sem conexão" : isLoading ? "Consultando…" : parsedInstances === null ? "Formato não reconhecido" : instancesWithDetailErrors > 0 ? "Consulta parcial" : "Consulta disponível"}</span>
        </div>
      </section>

      {!error && instancesWithDetailErrors > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          A lista de instâncias foi carregada, mas algumas consultas detalhadas foram recusadas. O status exibido em cada linha ajuda a identificar qual informação não foi retornada.
        </div>
      )}

      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-2.5 text-slate-600" />
        <input
          value={query}
          onChange={(event) => { setQuery(event.target.value); setPage(1); }}
          aria-label="Buscar instâncias AppRunCloud"
          placeholder="Buscar por conta, dispositivo ou identificador…"
          className="input !mt-0 pl-8"
        />
      </div>

      {error ? (
        <div className="flex items-start gap-2 rounded-md border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" /> {errorMessage}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-surface-border">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead className="bg-surface-raised/60 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2">Instância</th>
                <th className="px-3 py-2">Contas Instagram</th>
                <th className="px-3 py-2">Dispositivo</th>
                <th className="px-3 py-2">Estado reportado</th>
                <th className="px-3 py-2">Consulta detalhada</th>
              </tr>
            </thead>
            <tbody>
              {visibleInstances.map((instance, index) => (
                <InstanceRow key={scalar(instance, ["id", "instance_id", "uuid"]) || (page - 1) * PAGE_SIZE + index}
                  instance={instance} busyId={detailBusyId} onBusyChange={setDetailBusyId} />
              ))}
              {!isLoading && filtered.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-xs text-slate-500">
                  {parsedInstances === null ? "A resposta chegou, mas o formato da lista não foi reconhecido." : instances.length === 0 ? "A consulta não retornou instâncias." : "Nenhuma instância corresponde à busca."}
                </td></tr>
              )}
              {isLoading && instances.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-xs text-slate-500">Carregando inventário…</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {!error && filtered.length > PAGE_SIZE && (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
          <span>Exibindo {firstVisible}–{lastVisible} de {filtered.length} instâncias</span>
          <div className="flex gap-1">
            <button onClick={() => setPage(Math.max(1, currentPage - 1))}
              disabled={currentPage <= 1} className="btn-ghost">
              <ChevronLeft size={12} /> Anterior
            </button>
            <span className="flex items-center px-2">Página {currentPage} de {pageCount}</span>
            <button onClick={() => setPage(Math.min(pageCount, currentPage + 1))}
              disabled={currentPage >= pageCount} className="btn-ghost">
              Próxima <ChevronRight size={12} />
            </button>
          </div>
        </div>
      )}
      <p className="text-[11px] text-slate-600">Dados consultados diretamente da AppRunCloud. A API enriquece até seis instâncias por consulta; as demais exibem os campos básicos retornados. Nenhuma alteração é enviada por esta tela.</p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="card"><p className="label">{label}</p><p className="metric mt-1">{value}</p></div>;
}

function InstanceRow({ instance, busyId, onBusyChange }: {
  instance: RecordValue;
  busyId: string | null;
  onBusyChange: (id: string | null) => void;
}) {
  const id = scalar(instance, ["id", "instance_id", "uuid"]);
  const validId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
  const [queryResult, setQueryResult] = useState<{
    source: RecordValue;
    accountData: unknown;
    instagramAccountsData: unknown;
    deviceData: unknown;
    accountError: boolean;
    instagramAccountsError: boolean;
    deviceError: boolean;
    accountStatus: number | null;
    instagramAccountsStatus: number | null;
    deviceStatus: number | null;
  } | null>(null);
  const currentQueryResult = queryResult?.source === instance ? queryResult : null;
  const accountData = currentQueryResult
    ? currentQueryResult.accountData
    : instance.account_detail ?? instance.account;
  const instagramAccountsData = currentQueryResult
    ? currentQueryResult.instagramAccountsData
    : instance.instagram_accounts_detail ?? instance.instagram_accounts ?? instance.accounts;
  const deviceData = currentQueryResult
    ? currentQueryResult.deviceData
    : instance.device_detail ?? instance.device;
  const accountError = currentQueryResult
    ? currentQueryResult.accountError
    : Boolean(instance.account_detail_error);
  const instagramAccountsError = currentQueryResult
    ? currentQueryResult.instagramAccountsError
    : Boolean(instance.instagram_accounts_error);
  const deviceError = currentQueryResult
    ? currentQueryResult.deviceError
    : Boolean(instance.device_detail_error);
  const accountStatus = currentQueryResult
    ? currentQueryResult.accountStatus
    : typeof instance.account_detail_upstream_status === "number" ? instance.account_detail_upstream_status : null;
  const instagramAccountsStatus = currentQueryResult
    ? currentQueryResult.instagramAccountsStatus
    : typeof instance.instagram_accounts_upstream_status === "number" ? instance.instagram_accounts_upstream_status : null;
  const deviceStatus = currentQueryResult
    ? currentQueryResult.deviceStatus
    : typeof instance.device_detail_upstream_status === "number" ? instance.device_detail_upstream_status : null;
  const [loading, setLoading] = useState(false);
  const [requestState, setRequestState] = useState<{ source: RecordValue; requested: boolean } | null>(null);
  const requested = requestState?.source === instance
    ? requestState.requested
    : Boolean(accountData || instagramAccountsData || deviceData || accountError || instagramAccountsError || deviceError);

  async function consultar() {
    if (!validId || loading || (busyId !== null && busyId !== id)) return;
    onBusyChange(id);
    setLoading(true);
    setRequestState({ source: instance, requested: true });
    try {
      const [accountResult, instagramAccountsResult, deviceResult] = await Promise.allSettled([
        api(`/v1/integrations/appruncloud/instances/${encodeURIComponent(id)}/account`),
        api(`/v1/integrations/appruncloud/instances/${encodeURIComponent(id)}/instagram/accounts`),
        api(`/v1/integrations/appruncloud/instances/${encodeURIComponent(id)}/device`),
      ]);
      setQueryResult({
        source: instance,
        accountData: accountResult.status === "fulfilled" ? accountResult.value : null,
        instagramAccountsData: instagramAccountsResult.status === "fulfilled" ? instagramAccountsResult.value : null,
        deviceData: deviceResult.status === "fulfilled" ? deviceResult.value : null,
        accountError: accountResult.status === "rejected",
        instagramAccountsError: instagramAccountsResult.status === "rejected",
        deviceError: deviceResult.status === "rejected",
        accountStatus: upstreamStatus(accountResult),
        instagramAccountsStatus: upstreamStatus(instagramAccountsResult),
        deviceStatus: upstreamStatus(deviceResult),
      });
    } finally {
      setLoading(false);
      onBusyChange(null);
    }
  }

  const account = nestedScalar(instance, ["account"], ["username", "handle", "name", "account"])
    || nestedScalar(asRecord(accountData) ?? {}, ["account", "data", "user", "instagram"], ["username", "handle", "name", "account"]);
  const accountRecords = extractAccounts(instagramAccountsData);
  const accountListIsNull = asRecord(instagramAccountsData)?.accounts === null;
  const accountNames = (accountRecords ?? []).map((item) =>
    nestedScalar(item, ["account", "user", "instagram"], ["username", "handle", "name", "account"]),
  ).filter(Boolean);
  const accountListLoaded = instagramAccountsData !== undefined && instagramAccountsData !== null && !instagramAccountsError;
  const device = nestedScalar(instance, ["device"], ["device_name", "model", "name", "label"])
    || nestedScalar(asRecord(deviceData) ?? {}, ["device", "data", "android"], ["device_name", "model", "name", "label"]);
  const state = nestedScalar(instance, ["device"], ["status", "state", "connection_status", "online"])
    || nestedScalar(asRecord(deviceData) ?? {}, ["device", "data", "android"], ["status", "state", "connection_status", "online"]);
  const accountLabel = accountError || instagramAccountsError
    ? upstreamErrorLabel(accountStatus ?? instagramAccountsStatus)
    : accountListLoaded
    ? accountRecords === null
      ? accountListIsNull
        ? "AppRunCloud retornou accounts=null"
        : "Formato da lista não reconhecido"
      : accountNames.length > 0
        ? accountNames.join(", ")
        : accountRecords.length > 0
          ? `${accountRecords.length} conta(s) logada(s)`
          : "Nenhuma conta logada"
    : account || (loading ? "Consultando…" : requested ? "Não informado" : "Não consultado");
  const deviceLabel = device || (loading ? "Consultando…" : deviceError ? upstreamErrorLabel(deviceStatus) : requested ? "Não informado" : "Não consultado");
  const stateLabel = state || (loading ? "Consultando…" : deviceError ? upstreamErrorLabel(deviceStatus) : requested ? "Estado não informado" : "Não consultado");

  return (
    <tr className="border-t border-surface-border hover:bg-surface-raised/40">
      <td className="px-3 py-2.5 font-mono text-xs text-slate-300">{id || "Identificador indisponível"}</td>
      <td className={`px-3 py-2.5 ${accountError || instagramAccountsError ? "text-amber-200" : "text-slate-300"}`}>{accountLabel}</td>
      <td className={`px-3 py-2.5 ${deviceError ? "text-amber-200" : "text-slate-400"}`}><span className="flex items-center gap-1.5"><Smartphone size={12} />{deviceLabel}</span></td>
      <td className={`px-3 py-2.5 text-xs ${deviceError ? "text-amber-200" : "text-slate-400"}`}>{stateLabel}</td>
      <td className="px-3 py-2.5">
        <button onClick={() => void consultar()} disabled={!validId || loading || (busyId !== null && busyId !== id)}
          title={!validId ? "A instância não tem um UUID válido para consultar detalhes." : busyId !== null && busyId !== id ? "Aguarde a consulta da outra instância." : undefined}
          className="btn-ghost whitespace-nowrap">
          {loading ? <Loader2 size={12} className="animate-spin" /> : validId ? <RefreshCw size={12} /> : <AlertTriangle size={12} />}
          {loading ? "Consultando…" : !validId ? "ID inválido" : requested ? "Consultar novamente" : "Consultar detalhes"}
        </button>
      </td>
    </tr>
  );
}

function upstreamStatus(result: PromiseSettledResult<unknown>): number | null {
  if (result.status !== "rejected" || !(result.reason instanceof Error)) return null;
  const match = result.reason.message.match(/\b(400|401|403|422|502|503)\b/);
  if (!match) return null;
  // O backend converte HTTP 400 do provedor em 422 para indicar rejeição de dados.
  return match[1] === "422" ? 400 : Number(match[1]);
}

function upstreamErrorLabel(status: number | null): string {
  return status === 400
    ? "AppRunCloud recusou a consulta (HTTP 400)"
    : status === 401 || status === 403
      ? `Acesso recusado (HTTP ${status})`
      : status
        ? `Falha na consulta (HTTP ${status})`
        : "Falha na consulta detalhada";
}

