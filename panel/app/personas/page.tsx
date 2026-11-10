"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Plus, User, Link2, Brain, Search, MapPin, Sparkles, BadgeCheck, ArrowUpRight } from "lucide-react";
import { api, mutate } from "@/lib/api";
import { PLATAFORMA, STATUS } from "@/lib/contas";
import { urlDaMidia } from "@/lib/api";

/**
 * Personas.
 *
 * A identidade, separada do login. A Luna Prado existe mesmo que nenhuma
 * conta exista — e o Instagram e o WhatsApp dela são a MESMA personagem,
 * com uma memória só.
 */
export default function Personas() {
  const [q, setQ] = useState("");
  const [nova, setNova] = useState(false);
  const { data, mutate: reload } = useSWR(
    `/v1/personas${q ? `?q=${encodeURIComponent(q)}` : ""}`, api,
  );
  const personas = data?.personas ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-indigo-300">Identidades do Olimpo</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-100">Personas</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Cada persona reúne uma história, uma rotina e uma ficha completa de comportamento para orientar as contas vinculadas.
          </p>
        </div>
        <button onClick={() => setNova((v) => !v)} className="btn-primary px-4 py-2.5">
          <Sparkles size={15} /> Gerar persona
        </button>
      </header>

      {nova && <FormPersona onSaved={() => { reload(); }} onClose={() => setNova(false)} />}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-border bg-surface/50 p-3">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <User size={14} className="text-indigo-300" />
          <span><strong className="text-slate-100">{personas.length}</strong> {personas.length === 1 ? "persona" : "personas"} nesta lista</span>
        </div>
        <div className="relative w-full sm:w-72">
          <Search size={14} className="absolute left-2.5 top-2.5 text-slate-600" />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="buscar por nome…" className="input !mt-0 pl-8" />
        </div>
      </div>

      {personas.length === 0 && !nova && (
        <div className="card flex flex-col items-center gap-3 py-12 text-center">
          <div className="rounded-full border border-indigo-300/20 bg-indigo-300/10 p-3 text-indigo-200"><Sparkles size={20} /></div>
          <div>
            <p className="font-medium text-slate-200">Sua primeira persona começa com uma história</p>
            <p className="mt-1 text-sm text-slate-500">Gere identidade, rotina, personalidade e ficha estruturada em uma chamada.</p>
          </div>
          <button onClick={() => setNova(true)} className="btn-primary"><Plus size={14} /> Criar persona</button>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {personas.map((p: any) => <CardPersona key={p.id} persona={p} />)}
      </div>
    </div>
  );
}

function CardPersona({ persona }: { persona: any }) {
  const contas = persona.accounts ?? [];
  const card = persona.persona_card ?? {};
  const identity = card?.identity ?? {};
  const niche = card?.niche ?? {};
  const lore = card?.lore ?? {};
  const city = identity?.location?.city;
  const summary = lore.backstory || lore.canonical_narrative || persona.description;
  const requiredBlocks = ["identity", "voice", "visual", "personality", "lore", "niche", "taboos", "cadence", "commercial"];
  const blockCount = requiredBlocks.filter((key) => card[key] && Object.keys(card[key]).length > 0).length;
  const semCard = Object.keys(card).length === 0;

  return (
    <article className="card overflow-hidden !p-0">
      <div className="space-y-4 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {persona.face_asset_id ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={urlDaMidia(persona.face_asset_id)} alt=""
              className="h-14 w-14 shrink-0 rounded-xl object-cover" />
          ) : (
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl border border-surface-border bg-gradient-to-br from-indigo-400/10 to-surface">
              <User size={20} className="text-indigo-200/70" />
            </div>
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate font-semibold text-slate-100">{persona.name}</span>
              {identity.handle && <span className="font-mono text-xs text-slate-500">@{String(identity.handle).replace(/^@/, "")}</span>}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
              {(persona.apparent_age || identity.apparent_age) && <span>{persona.apparent_age || identity.apparent_age} anos</span>}
              {persona.gender && <span>{persona.gender}</span>}
              {city && <span className="flex items-center gap-1"><MapPin size={11} />{city}{identity.location?.state ? `, ${identity.location.state}` : ""}</span>}
            </div>
          </div>
        </div>
        <span className={`flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-[10px] ${blockCount === requiredBlocks.length ? "border-emerald-400/20 bg-emerald-400/5 text-emerald-200" : "border-amber-400/20 bg-amber-400/5 text-amber-200"}`}>
          <BadgeCheck size={11} /> {blockCount}/{requiredBlocks.length} blocos
        </span>
      </div>

      {niche.primary && <p className="w-fit rounded-full border border-indigo-300/20 bg-indigo-300/5 px-2.5 py-1 text-xs text-indigo-100">{niche.primary}</p>}
      {summary && <p className="line-clamp-3 text-sm leading-relaxed text-slate-400">{summary}</p>}

      {semCard && <p className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-amber-100">Esta persona ainda não tem uma ficha estruturada.</p>}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surface-border bg-surface/40 px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs text-slate-400"><Link2 size={12} /> {contas.length}/2 contas</span>
          {contas.slice(0, 2).map((c: any) => {
            const plat = PLATAFORMA[c.platform] ?? { cor: "", rotulo: c.platform };
            return <Link key={c.id} href={`/contas/${c.id}`} className={`rounded border px-2 py-1 text-[10px] ${plat.cor}`}>
              {plat.rotulo} · {c.handle} · {STATUS[c.status]?.rotulo ?? c.status}
            </Link>;
          })}
          {!contas.length && <span className="text-xs text-slate-600">sem contas vinculadas</span>}
        </div>
        <Link href={`/personas/${persona.id}`} className="flex items-center gap-1 text-xs font-medium text-indigo-200 hover:text-white">
          Abrir ficha <ArrowUpRight size={13} />
        </Link>
      </div>
    </article>
  );
}

function FormPersona({ onSaved, onClose }: { onSaved: () => void; onClose: () => void }) {
  const [f, setF] = useState({ name: "", city: "", age: "" });
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [resultado, setResultado] = useState<any>(null);

  async function salvar() {
    if (f.age && Number(f.age) < 18) {
      setErro("A idade mínima para gerar uma persona é 18 anos.");
      return;
    }
    setSalvando(true); setErro(null);
    try {
      const response = await mutate("/v1/personas/generate", "POST", {
        ...(f.name.trim() ? { name: f.name.trim() } : {}),
        ...(f.city.trim() ? { city: f.city.trim() } : {}),
        ...(f.age ? { age: Number(f.age) } : {}),
      });
      setResultado(response);
      onSaved();
    } catch (e) { setErro(String(e)); setSalvando(false); }
  }

  return (
    <div className="card space-y-3">
      <span className="label">Gerar nova persona com Gemini Flash</span>
      {resultado ? (
        <div className="space-y-3">
          <p className="text-sm text-emerald-300">
            Persona <strong>{resultado.persona?.name}</strong> criada e salva.
          </p>
          <p className="font-mono text-xs text-slate-400">
            Modelo {resultado.usage?.model} · entrada {resultado.usage?.input_tokens} tokens · saída {resultado.usage?.output_tokens} · total {resultado.usage?.total_tokens}
          </p>
          <div className="max-h-64 overflow-auto whitespace-pre-wrap rounded border border-surface-border p-3 text-sm text-slate-300">
            {resultado.narrative}
          </div>
          <div className="flex gap-2">
            <Link href={`/personas/${resultado.persona?.id}`} className="btn-primary">Abrir ficha</Link>
            <button onClick={() => { setResultado(null); setF({ name: "", city: "", age: "" }); setSalvando(false); }} className="btn-ghost">Gerar outra</button>
            <button onClick={onClose} className="btn-ghost">Concluir</button>
          </div>
        </div>
      ) : <>
      <p className="text-xs text-slate-500">
        Nome, cidade e idade são opcionais. Se informar um valor, ele será mantido na geração. A persona será salva automaticamente após as validações.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="label">Nome (opcional)</span>
          <input className="input" placeholder="Luna Prado" value={f.name}
            onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={120} />
        </label>
        <label className="block">
          <span className="label">Cidade (opcional)</span>
          <input className="input" placeholder="Florianópolis" value={f.city}
            onChange={(e) => setF({ ...f, city: e.target.value })} maxLength={120} />
        </label>
        <label className="block">
          <span className="label">Idade (opcional, mínimo 18)</span>
          <input className="input" type="number" min={18} max={100} placeholder="28" value={f.age}
            onChange={(e) => setF({ ...f, age: e.target.value })} />
        </label>
      </div>
      <p className="flex items-start gap-1.5 text-xs text-slate-600">
        <Brain size={12} className="mt-0.5 shrink-0" />
        Uma única chamada gera a história completa e o persona card, incluindo rotina, preferências, princípios e horários realistas para uso do celular.
      </p>
      {erro && <p className="font-mono text-xs text-red-300">{erro}</p>}
      <div className="flex gap-2">
        <button onClick={salvar} disabled={salvando} className="btn-primary">
          {salvando ? "gerando e salvando…" : "Gerar persona"}
        </button>
        <button onClick={onClose} disabled={salvando} className="btn-ghost">Cancelar</button>
      </div>
      </>}
    </div>
  );
}
