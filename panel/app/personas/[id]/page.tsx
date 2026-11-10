"use client";

import { useState, use, useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, Save, Code2, User } from "lucide-react";
import useSWR from "swr";
import { api, mutate } from "@/lib/api";
import { tempoRelativo } from "@/lib/contas";
import { IdentidadeVisual, Figurinos } from "@/components/identidade-visual";
import { FotosDeReferencia } from "@/components/fotos-referencia";
import { MidiasDaPersona } from "@/components/midias-da-persona";
import { EstudioDaPersona } from "@/components/estudio-da-persona";
import { PersonaFicha } from "@/components/persona-ficha";
import { PersonaLogins } from "@/components/persona-logins";
import { Abas } from "@/components/abas";

/**
 * Ficha da persona.
 *
 * A história e a ficha vêm primeiro para que a identidade da personagem fique
 * clara antes da produção visual. As quatro âncoras continuam na página, com
 * acesso direto, para manter o rosto consistente nas gerações de mídia.
 *
 * Estúdio, mídias, figurinos e logins ficam em abas. O
 * estúdio morava numa página própria com um seletor de personas no topo, e
 * isso invertia a relação: a persona é o sujeito, a foto é o que se faz com
 * ela. Escolher a personagem numa tela separada obrigava a sair da ficha,
 * perder o contexto das âncoras e dos figurinos, e voltar. Uma persona
 * tem campos demais para empilhar: montar tudo de uma vez empurra as imagens
 * para fora da tela e dispara todas as requisições juntas.
 */
export default function FichaDaPersona({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, mutate: reload } = useSWR(`/v1/personas/${id}`, api);

  const [card, setCard] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [json, setJson] = useState(false);
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const persona = data?.persona;
  const cardAtual = persona?.persona_card ?? {};
  const identity = cardAtual.identity ?? {};
  const lore = cardAtual.lore ?? {};
  const narrative = lore.canonical_narrative || lore.backstory || "";

  useEffect(() => {
    if (!persona) return;
    setCard(persona.persona_card ?? {});
    setTexto(JSON.stringify(persona.persona_card ?? {}, null, 2));
    setMeta({
      name: persona.name, description: persona.description ?? "",
      notes: persona.notes ?? "",
    });
  }, [persona?.id, persona?.updated_at]);

  if (!persona || !card || !meta) return <p className="text-sm text-slate-500">carregando…</p>;

  async function salvar() {
    setSalvando(true); setErro(null);
    try {
      let final = card;
      if (json) {
        try { final = JSON.parse(texto); }
        catch (e) { setErro(`JSON inválido: ${e}`); setSalvando(false); return; }
      }
      await mutate(`/v1/personas/${id}`, "PATCH", { ...meta, persona_card: final });
      await reload();
    } catch (e) { setErro(String(e)); } finally { setSalvando(false); }
  }

  return (
    <div className="space-y-5">
      <Link href="/personas" className="flex w-fit items-center gap-1 text-xs text-slate-500 hover:text-slate-300">
        <ArrowLeft size={12} /> personas
      </Link>

      <header className="flex items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <User size={16} className="text-indigo-300" />
            <h1 className="text-xl font-semibold text-slate-100">{persona.name}</h1>
            <span className="rounded-full border border-surface-border px-2 py-0.5 font-mono text-[10px] text-slate-500">ficha v{persona.persona_version}</span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {[identity.occupation, identity.location?.city, identity.apparent_age ? `${identity.apparent_age} anos` : null].filter(Boolean).join(" · ")}
            {data.accounts.length ? ` · ${data.accounts.length} conta${data.accounts.length === 1 ? "" : "s"} vinculada${data.accounts.length === 1 ? "" : "s"}` : " · sem contas vinculadas"}
            {` · atualizada ${tempoRelativo(persona.updated_at)}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => {
            if (!json) setTexto(JSON.stringify(card, null, 2));
            else { try { setCard(JSON.parse(texto)); } catch { /* mantém */ } }
            setJson(!json);
          }} className="btn-ghost">
            <Code2 size={13} /> {json ? "editor guiado" : "JSON"}
          </button>
          <button onClick={salvar} disabled={salvando} className="btn-primary">
            <Save size={14} /> {salvando ? "salvando…" : "Salvar"}
          </button>
        </div>
      </header>

      {erro && <p className="font-mono text-xs text-red-300">{erro}</p>}

      {narrative && (
        <section className="card space-y-3 border-indigo-300/15 bg-gradient-to-br from-indigo-400/[0.06] to-surface">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="label">História e momento atual</span>
              <p className="mt-1 text-xs text-slate-500">A base que orienta a rotina, a voz e as decisões da personagem.</p>
            </div>
            {cardAtual.niche?.primary && <span className="hidden rounded-full border border-indigo-300/20 px-2.5 py-1 text-[10px] text-indigo-100 sm:inline">{cardAtual.niche.primary}</span>}
          </div>
          <details className="group">
            <summary className="cursor-pointer list-none text-sm leading-relaxed text-slate-300">
              <span className="line-clamp-4 whitespace-pre-wrap">{narrative}</span>
              <span className="mt-2 inline-block text-xs font-medium text-indigo-200 group-open:hidden">Ler história completa ↓</span>
              <span className="mt-2 hidden text-xs font-medium text-indigo-200 group-open:inline-block">Recolher história ↑</span>
            </summary>
            <div className="mt-3 whitespace-pre-wrap border-t border-surface-border pt-3 text-sm leading-relaxed text-slate-300">{narrative}</div>
          </details>
        </section>
      )}

      {/* ─────────────────────────────────────────────── identidade, no topo
          Fora das abas de propósito: é o que se olha antes de qualquer outra
          coisa, e o que precisa estar à mão enquanto se mexe no resto. */}
      <IdentidadeVisual personaId={id} persona={persona} />

      {/* Logo abaixo das âncoras porque é essa a hierarquia: sem rosto elas
          não salvam nada, e com rosto melhoram toda geração. */}
      <FotosDeReferencia personaId={id} />

      {/* ──────────────────────────────────────────────────────── o resto */}
      <Abas
        abas={[
          {
            chave: "ficha", rotulo: "Ficha da persona",
            conteudo: () => (
              <PersonaFicha
                card={card} meta={meta} json={json} texto={texto}
                onCard={setCard} onMeta={setMeta} onTexto={setTexto}
              />
            ),
          },
          {
            chave: "estudio", rotulo: "Estúdio",
            conteudo: () => <EstudioDaPersona personaId={id} />,
          },
          {
            chave: "midias", rotulo: "Mídias",
            conteudo: () => <MidiasDaPersona personaId={id} />,
          },
          {
            chave: "figurinos", rotulo: "Figurinos",
            conteudo: () => <Figurinos personaId={id} persona={persona} />,
          },
          {
            chave: "logins", rotulo: "Logins", contagem: data.accounts.length,
            conteudo: () => <PersonaLogins contas={data.accounts} />,
          },
        ]}
      />
    </div>
  );
}
