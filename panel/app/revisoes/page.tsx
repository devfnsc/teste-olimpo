"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { extractAccounts, extractInstances, type AppRunCloudRecord } from "@/lib/appruncloud";

type RecordValue = Record<string, unknown>;

function asRecord(value: unknown): RecordValue | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as RecordValue
    : null;
}

function readScalar(value: unknown, keys: string[], depth = 0): string {
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = readScalar(item, keys, depth + 1);
      if (found) return found;
    }
    return "";
  }
  const record = asRecord(value);
  if (!record) return "";
  for (const key of keys) {
    const field = record[key];
    if (typeof field === "string" || typeof field === "number") return String(field);
  }
  if (depth >= 5) return "";
  for (const field of Object.values(record)) {
    const found = readScalar(field, keys, depth + 1);
    if (found) return found;
  }
  return "";
}

function accountSummary(instance: AppRunCloudRecord): string {
  if (instance.instagram_accounts_error) return "Falha ao consultar a lista";
  const payload = instance.instagram_accounts_detail ?? instance.instagram_accounts ?? instance.accounts;
  if (payload === undefined || payload === null) return "Detalhe não consultado";
  const record = asRecord(payload);
  if (record && record.accounts === null) return "API retornou accounts=null";
  const accounts = extractAccounts(payload);
  if (accounts === null) return "Formato não reconhecido";
  if (accounts.length === 0) return "Nenhuma conta retornada";
  return accounts.map((account) => readScalar(account, ["username", "handle", "name"])).filter(Boolean).join(", ")
    || `${accounts.length} conta(s) retornada(s)`;
}

function detailStatus(instance: AppRunCloudRecord): { label: string; failed: boolean } {
  const failed = Boolean(instance.account_detail_error || instance.instagram_accounts_error || instance.device_detail_error);
  const hasDetails = Boolean(instance.account_detail || instance.instagram_accounts_detail || instance.device_detail);
  return {
    label: failed ? "Detalhes com falha" : hasDetails ? "Detalhes recebidos" : "Somente inventário",
    failed,
  };
}

export default function RevisoesPage() {
  const { data, error, isLoading, mutate, isValidating } = useSWR(
    "/v1/integrations/appruncloud/instances?include_details=true&detail_limit=6",
    api,
    { refreshInterval: 60_000 },
  );
  const instances = useMemo(() => extractInstances(data) ?? [], [data]);
  const details = instances.filter((instance) =>
    instance.account_detail || instance.instagram_accounts_detail || instance.device_detail ||
    instance.account_detail_error || instance.instagram_accounts_error || instance.device_detail_error,
  ).length;
  const failures = instances.filter((instance) => detailStatus(instance).failed).length;

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">AppRunCloud · consulta de leitura</div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Revisões</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Confira o inventário e os detalhes retornados pela API. Esta tela não cria personas nem altera contas.
          </p>
        </div>
        <button className="btn-ghost" onClick={() => void mutate()} disabled={isValidating}>
          {isValidating ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Atualizar consulta
        </button>
      </header>

      {error && <div role="alert" className="rounded-md border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-sm text-rose-200">Não foi possível carregar o inventário AppRunCloud. Confira a conexão local e tente novamente.</div>}

      <section className="grid gap-3 sm:grid-cols-3">
        <Metric label="Instâncias retornadas" value={isLoading ? "…" : instances.length} />
        <Metric label="Com detalhes consultados" value={isLoading ? "…" : details} />
        <Metric label="Consultas detalhadas com falha" value={isLoading ? "…" : failures} alert={failures > 0} />
      </section>

      <section className="card overflow-hidden !p-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border px-4 py-3">
          <div><h2 className="text-sm font-semibold text-slate-100">Instâncias AppRunCloud</h2><p className="mt-0.5 text-xs text-slate-500">A API enriquece até seis instâncias por consulta.</p></div>
          <span className="text-xs text-slate-500">Atualização automática a cada minuto</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-surface-raised/60 text-xs text-slate-500"><tr>
              <th className="px-3 py-2.5 font-medium">Instância</th><th className="px-3 py-2.5 font-medium">Conta Instagram</th>
              <th className="px-3 py-2.5 font-medium">Dispositivo</th><th className="px-3 py-2.5 font-medium">Estado informado</th>
              <th className="px-3 py-2.5 font-medium">Resultado da consulta</th>
            </tr></thead>
            <tbody>
              {isLoading && <tr><td colSpan={5} className="px-3 py-10 text-center text-sm text-slate-500"><Loader2 size={15} className="mr-2 inline animate-spin" />Consultando inventário…</td></tr>}
              {!isLoading && !error && instances.length === 0 && <tr><td colSpan={5} className="px-3 py-10 text-center text-sm text-slate-500">Nenhuma instância retornada.</td></tr>}
              {instances.map((instance, index) => {
                const id = readScalar(instance, ["id", "instance_id", "uuid"]) || `instância-${index + 1}`;
                const label = readScalar(instance, ["label", "name", "app_name"]) || id;
                const account = readScalar(instance.account_detail ?? instance, ["username", "handle"])
                  || readScalar(instance.account_detail ?? instance, ["name"])
                  || accountSummary(instance);
                const device = readScalar(instance.device_detail ?? instance, ["device_name", "model", "device_model"])
                  || readScalar(instance.device_detail ?? instance, ["name"])
                  || "Não informado";
                const state = readScalar(instance, ["state", "status", "connection_status"]) || "Não informado";
                const detail = detailStatus(instance);
                return <tr key={id} className="border-t border-surface-border align-top hover:bg-surface-raised/30">
                  <td className="max-w-64 px-3 py-3"><div className="truncate text-slate-200" title={label}>{label}</div><div className="mt-1 break-all font-mono text-[10px] text-slate-600">{id}</div></td>
                  <td className="max-w-64 px-3 py-3 text-slate-300">{account}</td>
                  <td className="max-w-56 px-3 py-3 text-slate-400">{device}</td>
                  <td className="px-3 py-3 text-slate-400">{state}</td>
                  <td className={`px-3 py-3 text-xs ${detail.failed ? "text-amber-200" : "text-slate-400"}`}>
                    {detail.failed ? <AlertTriangle size={13} className="mr-1 inline" /> : detail.label === "Detalhes recebidos" ? <CheckCircle2 size={13} className="mr-1 inline text-emerald-300" /> : null}
                    {detail.label}
                  </td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>
        <div className="border-t border-surface-border px-4 py-3 text-xs text-slate-600">Dados exibidos conforme retornados pela AppRunCloud. Nenhuma alteração é enviada por esta tela.</div>
      </section>
    </div>
  );
}

function Metric({ label, value, alert = false }: { label: string; value: number | string; alert?: boolean }) {
  return <div className="card"><div className="label">{label}</div><div className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${alert ? "text-amber-200" : "text-slate-100"}`}>{value}</div></div>;
}

