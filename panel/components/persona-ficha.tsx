"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

const GROUPS = [
  { id: "lore", title: "História e rotina", description: "A trajetória, o momento atual e os horários reais da persona.", blocks: ["lore"] },
  { id: "identity", title: "Identidade", description: "Como ela se apresenta e os dados fixos da personagem.", blocks: ["identity"] },
  { id: "personality", title: "Personalidade", description: "Traços, valores, opiniões e o que a move ou incomoda.", blocks: ["personality"] },
  { id: "voice", title: "Voz e escrita", description: "Vocabulário, tom, exemplos e limites de linguagem.", blocks: ["voice"] },
  { id: "content", title: "Conteúdo e frequência", description: "Temas, público, formatos e ritmo editorial.", blocks: ["niche", "cadence"] },
  { id: "visual", title: "Direção visual", description: "Estética e regras visuais. As imagens de identidade ficam na seção acima.", blocks: ["visual"] },
  { id: "limits", title: "Limites e publicidade", description: "Regras de interação, assuntos sensíveis e parcerias comerciais.", blocks: ["taboos", "commercial"] },
  { id: "extra", title: "Campos adicionais", description: "Blocos específicos de outros tipos de persona.", blocks: ["editorial", "curation"] },
];

const BLOCK_TITLES: Record<string, string> = {
  identity: "Identidade", lore: "História e rotina", personality: "Personalidade",
  voice: "Voz e escrita", niche: "Nicho e público", cadence: "Frequência",
  visual: "Direção visual", taboos: "Limites e interações", commercial: "Publicidade",
  editorial: "Política editorial", curation: "Curadoria",
};

const LABELS: Record<string, string> = {
  name: "Nome completo", display_name: "Nome de exibição", handle: "Identificador sugerido",
  apparent_age: "Idade aparente", gender: "Gênero", location: "Localização",
  city: "Cidade", state: "Estado", country: "País", neighborhood: "Região ou bairro (sem endereço)",
  occupation: "Ocupação", language: "Idioma", pronouns: "Pronomes", bio: "Bio", ai_disclosure: "Aviso de personagem virtual",
  backstory: "História resumida", canonical_narrative: "História completa gerada", milestones: "Marcos da vida",
  when: "Quando", what: "O que aconteceu", age: "Idade na ocasião", event: "Acontecimento", impact: "Impacto",
  routine: "Rotina", phone_schedule: "Janelas para usar o celular", days: "Dias", start: "Início", end: "Fim",
  context: "Contexto", phone_activities: "O que costuma fazer no celular", current_situation: "Momento atual",
  relationships: "Relações importantes", family: "Família", friends: "Amizades", pets: "Animais de estimação",
  traits: "Traços", values: "Valores e princípios", irritations: "O que incomoda", moves_her: "O que a emociona",
  default_mood: "Humor mais comum", mood_range: "Variações de humor", humor: "Tipo de humor", insecurities: "Inseguranças",
  opinions: "Opiniões", tone: "Tom de voz", register: "Nível de formalidade", capitalization: "Uso de maiúsculas",
  slang: "Vocabulário característico", uses: "Expressões que usa", never: "Expressões que evita",
  caption_length: "Tamanho de texto", typical: "Tamanho típico (caracteres)", min: "Mínimo", max: "Máximo",
  min_words: "Mínimo de palavras", max_words: "Máximo de palavras", emoji: "Emojis", usage: "Frequência de uso",
  max_per_caption: "Máximo por texto", allowed: "Permitidos", banned: "Evitar", hashtag: "Hashtags", count: "Quantidade",
  always: "Sempre usar", never_say: "Frases que nunca diz", examples: "Exemplos de escrita", cta_style: "Chamadas para ação",
  punctuation: "Pontuação", exclamation: "Exclamação", ellipsis: "Reticências", caps_lock: "Caixa alta",
  primary: "Tema principal", secondary: "Temas secundários", audience: "Público", description: "Descrição",
  age_range: "Faixa etária", regions: "Regiões", pain_points: "Dificuldades do público", content_pillars: "Pilares de conteúdo",
  share: "Proporção (0 a 1)", example: "Exemplo de pauta", formats: "Formatos preferidos", references: "Referências de estilo",
  topics: "Temas sensíveis ou proibidos", banned_words: "Palavras a evitar", never_interactions: "Interações que não realiza",
  sensitive_handling: "Como lidar com assuntos sensíveis", health: "Saúde", money: "Dinheiro", romance: "Romance",
  harassment: "Assédio", hard_blocks: "Bloqueios absolutos", posts_per_day: "Publicações por dia",
  stories_per_day: "Stories por dia", reels_per_week: "Reels por semana", preferred_hours: "Horários preferidos",
  story_hours: "Horários para stories", most_active_days: "Dias mais ativos", quiet_days: "Dias de descanso",
  reply_window_minutes: "Prazo típico de resposta (minutos)", burst_tolerance: "Tolerância a sequência de posts",
  notes: "Observações", canonical_description: "Descrição visual canônica", aesthetic: "Estética fotográfica",
  palette: "Paleta de cores", mood: "Clima da paleta", recurring_settings: "Cenários recorrentes", wardrobe: "Figurino",
  staples: "Peças frequentes", colors: "Cores de roupa", forbidden_visuals: "Elementos visuais proibidos",
  body_language: "Postura e expressão", shot_types: "Enquadramentos frequentes", accepts_sponsored: "Aceita publicidade",
  allowed_categories: "Categorias permitidas", blocked_categories: "Categorias bloqueadas", disclosure: "Identificação da publicidade",
  required: "Obrigatória", method: "Forma de identificação", text: "Texto de identificação", position: "Posição no texto",
  tone_in_ads: "Tom em publicidade", max_sponsored_per_month: "Máximo de publis por mês", affiliate: "Afiliados",
  enabled: "Ativado", schema_version: "Versão do formato", version: "Versão da ficha", archetype: "Tipo de persona",
};

function nomeCampo(key: string) {
  return LABELS[key] ?? key.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function templateParaArray(path: string): Record<string, unknown> {
  if (path.endsWith("milestones")) return { age: "", event: "", impact: "" };
  if (path.endsWith("phone_schedule")) return { days: "", start: "", end: "", context: "", phone_activities: "" };
  if (path.endsWith("content_pillars")) return { name: "", share: 0, example: "" };
  if (path.endsWith("family") || path.endsWith("friends") || path.endsWith("relationships")) {
    return { name: "", relation: "", detail: "" };
  }
  if (path.endsWith("pets")) return { name: "", kind: "", detail: "" };
  return {};
}

function atualizarCaminho(root: any, path: (string | number)[], value: any): any {
  if (!path.length) return value;
  const [head, ...rest] = path;
  const copy = Array.isArray(root) ? [...root] : { ...(root ?? {}) };
  copy[head] = atualizarCaminho(copy[head], rest, value);
  return copy;
}

/** Editor recursivo: também permite alterar campos recém-gerados sem perder a estrutura. */
function Campo({ label, value, path, onChange }: {
  label: string; value: any; path: (string | number)[]; onChange: (path: (string | number)[], value: any) => void;
}) {
  const pathText = path.map(String).join(".");

  if (Array.isArray(value)) {
    const objetos = value.some((item) => item !== null && typeof item === "object");
    if (!objetos) {
      const numerica = (value.length > 0 && value.every((item) => typeof item === "number"))
        || /\.(age_range|preferred_hours|story_hours|count)$/.test(pathText);
      return (
        <label className="block">
          <span className="label">{label}</span>
          <textarea className="input min-h-20 font-mono text-xs" value={value.join("\n")}
            placeholder="um item por linha"
            onChange={(event) => onChange(path, event.target.value.split("\n").map((item) => item.trim()).filter(Boolean).map((item) => numerica ? Number(item) : item))} />
          <span className="mt-1 block text-[10px] text-slate-600">Um item por linha</span>
        </label>
      );
    }
    return (
      <div className="space-y-2 rounded-lg border border-surface-border bg-surface/40 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="label">{label} <span className="text-slate-600">({value.length})</span></span>
          <button type="button" className="btn-ghost !px-2 !py-1 text-xs"
            onClick={() => onChange(path, [...value, templateParaArray(pathText)])}>
            <Plus size={12} /> Adicionar
          </button>
        </div>
        {value.map((item: any, index: number) => (
          <div key={`${pathText}-${index}`} className="rounded-md border border-surface-border bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">Item {index + 1}</span>
              <button type="button" title="Remover item" className="text-slate-600 hover:text-red-300"
                onClick={() => onChange(path, value.filter((_: unknown, i: number) => i !== index))}><Trash2 size={13} /></button>
            </div>
            <Campo label="" value={item} path={[...path, index]} onChange={onChange} />
          </div>
        ))}
        {!value.length && <p className="text-xs text-slate-600">Nenhum item ainda.</p>}
      </div>
    );
  }

  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    return (
      <div className="space-y-3 rounded-lg border border-surface-border bg-surface/40 p-3">
        {label && <span className="label">{label}</span>}
        {entries.length ? entries.map(([key, child]) => (
          <Campo key={`${pathText}.${key}`} label={nomeCampo(key)} value={child}
            path={[...path, key]} onChange={onChange} />
        )) : <p className="text-xs text-slate-600">Sem campos estruturados.</p>}
      </div>
    );
  }

  if (typeof value === "boolean") {
    return (
      <label className="flex items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface/40 px-3 py-2">
        <span className="label !mb-0">{label}</span>
        <input type="checkbox" checked={value} onChange={(event) => onChange(path, event.target.checked)} className="h-4 w-4 accent-indigo-400" />
      </label>
    );
  }

  const longo = typeof value === "string" && (value.length > 110 || value.includes("\n") || /story|narrative|backstory|description|context|activities|bio|detail|what|example|policy|handling|situation|routine/i.test(String(path.at(-1))));
  return (
    <label className="block">
      {label && <span className="label">{label}</span>}
      {longo ? (
        <textarea className={`input ${pathText.endsWith("canonical_narrative") ? "min-h-72" : "min-h-20"}`} value={value ?? ""}
          onChange={(event) => onChange(path, event.target.value)} />
      ) : (
        <input className="input" type={typeof value === "number" ? "number" : "text"} value={value ?? ""}
          onChange={(event) => onChange(path, typeof value === "number" ? Number(event.target.value) : event.target.value)} />
      )}
    </label>
  );
}

export function PersonaFicha({ card, meta, json, texto, onCard, onMeta, onTexto }: {
  card: any;
  meta: any;
  json: boolean;
  texto: string;
  onCard: (c: any) => void;
  onMeta: (m: any) => void;
  onTexto: (t: string) => void;
}) {
  const [grupoAtivo, setGrupoAtivo] = useState("lore");
  const grupo = GROUPS.find((item) => item.id === grupoAtivo) ?? GROUPS[0];

  function alterar(path: (string | number)[], value: any) {
    onCard(atualizarCaminho(card, path, value));
  }

  const extraBlocks = Object.keys(card ?? {}).filter((key) =>
    !["schema_version", "version", "archetype", ...GROUPS.flatMap((item) => item.blocks)].includes(key),
  );

  return (
    <div className="space-y-4">
      <section className="card grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block">
          <span className="label">Nome da persona</span>
          <input className="input" value={meta.name} onChange={(event) => onMeta({ ...meta, name: event.target.value })} />
        </label>
        <label className="block sm:col-span-2">
          <span className="label">Resumo do perfil</span>
          <input className="input" value={meta.description} onChange={(event) => onMeta({ ...meta, description: event.target.value })} />
        </label>
        <label className="block">
          <span className="label">Anotações internas</span>
          <input className="input" value={meta.notes} onChange={(event) => onMeta({ ...meta, notes: event.target.value })} />
        </label>
      </section>

      {json ? (
        <section className="card space-y-3">
          <div>
            <span className="label">Ficha completa em JSON</span>
            <p className="text-xs text-slate-500">Edição avançada da estrutura inteira. O modo guiado preserva os campos que o Gemini criou.</p>
          </div>
          <textarea value={texto} onChange={(event) => onTexto(event.target.value)} spellCheck={false}
            className="input min-h-[40rem] w-full font-mono text-xs leading-relaxed" />
        </section>
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {GROUPS.map((item) => (
              <button key={item.id} type="button" onClick={() => setGrupoAtivo(item.id)}
                className={`rounded-lg border px-3 py-2 text-left transition ${grupoAtivo === item.id ? "border-indigo-400/50 bg-indigo-400/10 text-indigo-100" : "border-surface-border bg-surface text-slate-400 hover:text-slate-200"}`}>
                <span className="block text-sm font-medium">{item.title}</span>
                <span className="mt-0.5 block text-[10px] text-slate-500">{item.blocks.length} {item.blocks.length === 1 ? "bloco" : "blocos"}</span>
              </button>
            ))}
          </div>

          <section className="card space-y-4">
            <header>
              <h2 className="text-base font-semibold text-slate-100">{grupo.title}</h2>
              <p className="mt-1 text-xs text-slate-500">{grupo.description}</p>
            </header>
            {grupo.blocks.map((block) => {
              const fields = card?.[block];
              return (
                <section key={block} className="space-y-3 border-t border-surface-border pt-4 first:border-0 first:pt-0">
                  <h3 className="text-sm font-medium text-slate-200">{BLOCK_TITLES[block]}</h3>
                  {fields && typeof fields === "object" ? Object.entries(fields).map(([key, value]) => (
                    <Campo key={`${block}.${key}`} label={nomeCampo(key)} value={value}
                      path={[block, key]} onChange={alterar} />
                  )) : (
                    <p className="rounded border border-amber-400/20 bg-amber-400/5 p-3 text-xs text-amber-200">
                      Este bloco ainda não existe na ficha. Use a edição JSON para adicioná-lo.
                    </p>
                  )}
                </section>
              );
            })}
            {grupoAtivo === "extra" && extraBlocks.map((block) => (
              <section key={block} className="space-y-3 border-t border-surface-border pt-4">
                <h3 className="text-sm font-medium text-slate-200">{BLOCK_TITLES[block] ?? nomeCampo(block)}</h3>
                {Object.entries(card[block] ?? {}).map(([key, value]) => (
                  <Campo key={`${block}.${key}`} label={nomeCampo(key)} value={value}
                    path={[block, key]} onChange={alterar} />
                ))}
              </section>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
