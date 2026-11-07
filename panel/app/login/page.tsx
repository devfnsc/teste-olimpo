"use client";

import { FormEvent, useState } from "react";
import { LockKeyhole } from "lucide-react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function entrar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail ?? "Não foi possível entrar.");
      }
      window.location.assign("/");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível entrar.");
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-5">
      <form onSubmit={entrar} className="card w-full max-w-sm space-y-4">
        <div className="flex items-center gap-2 text-slate-100">
          <LockKeyhole size={18} className="text-info" />
          <h1 className="text-lg font-semibold">Acesso ao Olimpo</h1>
        </div>
        <p className="text-sm text-slate-400">Informe a senha de acesso para abrir o painel.</p>
        <label className="block">
          <span className="label">Senha</span>
          <input
            autoFocus
            autoComplete="current-password"
            type="password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="input"
          />
        </label>
        {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
        <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
          {loading ? "verificando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}

