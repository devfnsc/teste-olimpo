export type AppRunCloudRecord = Record<string, unknown>;

function asRecord(value: unknown): AppRunCloudRecord | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as AppRunCloudRecord
    : null;
}

/** Aceita a lista direta da API e wrappers usuais, sem tratar formatos desconhecidos como lista vazia. */
export function extractInstances(payload: unknown, depth = 0): AppRunCloudRecord[] | null {
  if (Array.isArray(payload)) {
    return payload.map(asRecord).filter((item): item is AppRunCloudRecord => item !== null);
  }
  if (depth >= 5) return null;

  const record = asRecord(payload);
  if (!record) return null;
  for (const key of ["data", "instances", "items", "results"]) {
    if (record[key] === undefined || record[key] === null) continue;
    const instances = extractInstances(record[key], depth + 1);
    if (instances !== null) return instances;
  }
  return null;
}

/** Lê a lista de contas de wrappers da resposta sem confundir objeto inválido com lista vazia. */
export function extractAccounts(payload: unknown, depth = 0): AppRunCloudRecord[] | null {
  if (Array.isArray(payload)) {
    return payload.map(asRecord).filter((item): item is AppRunCloudRecord => item !== null);
  }
  if (depth >= 5) return null;

  const record = asRecord(payload);
  if (!record) return null;
  for (const key of ["accounts", "data", "items", "results"]) {
    if (record[key] === undefined || record[key] === null) continue;
    const accounts = extractAccounts(record[key], depth + 1);
    if (accounts !== null) return accounts;
  }
  return null;
}

