Warning: truncated output (original token count: 40851)
Total output lines: 2354

# 02 — Modelo de dados

> Fonte da verdade: os arquivos em [`db/migrations/`](../db/migrations/) — [`0001_initial.sql`](../db/migrations/0001_initial.sql) para o núcleo, [`0002_orchestrator_nodes.sql`](../db/migrations/0002_orchestrator_nodes.sql) para a ligação com o orchestrator, [`0005_servers_and_services.sql`](../db/migrations/0005_servers_and_services.sql) e [`0006_account_inventory.sql`](../db/migrations/0006_account_inventory.sql) para servidores, serviços, devices e inventário de contas, [`0007_personas_e_contas.sql`](../db/migrations/0007_personas_e_contas.sql) para a separação entre persona, login e lugar onde ele roda ([ADR-0013](adr/0013-persona-separada-da-conta.md)), e [`0008_absorve_maquina_de_influencers.sql`](../db/migrations/0008_absorve_maquina_de_influencers.sql) para a identidade **visual** — mídia, guarda-roupa, marcas e fila de geração ([ADR-0014](adr/0014-absorver-a-maquina-de-influencers.md)).
> Este documento **descreve** aqueles arquivos. Se os dois divergirem, o SQL vence e este documento está com bug.

Postgres 16 + três extensões: `uuid-ossp` (chaves), `vector` (pgvector, memória semântica), `pg_trgm` (busca aproximada em texto — dedup e QA de caption).

**Índice**

1. [Princípios do modelo](#1-princípios-do-modelo)
2. [Mapa de relacionamentos](#2-mapa-de-relacionamentos)
3. [Tabelas](#3-tabelas)
4. [ENUMs e máquinas de estado](#4-enums-e-máquinas-de-estado)
5. [Índices](#5-índices)
6. [Consultas de referência](#6-consultas-de-referência)
7. [Convenções de migração](#7-convenções-de-migração)

---

## 1. Princípios do modelo

### 1.1 Campos dormentes nascem na v1

O schema da Fase 0 já contém colunas e tabelas inteiras que **nenhuma linha de código lê na Fase 1**: `sources`, `ingested_items`, `monitors`, `monitor_hits`, `clients`, e as colunas `content_items.source_refs`, `attribution`, `claim_status`, `accounts.client_id`.

Isso é deliberado. O raciocínio:

- **O custo hoje é zero.** Uma coluna `nullable` com default e uma tabela vazia não custam performance, não custam manutenção e não confundem quem lê o SQL — porque estão marcadas `[DORMENTE]`.
- **O custo depois é alto.** Adicionar `rights_status NOT NULL` em `content_items` com 200 mil linhas e 50 contas em produção significa: janela de manutenção, backfill, revisão de todo código que faz `INSERT`, e um período em que metade do sistema conhece a coluna e a outra metade não.
- **O schema é o contrato do produto inteiro, não da fase atual.** O PLANO já sabe que a Fase 4 (fofoca) precisa de `claim_status` e a Fase 5 (clipagem) precisa de `rights_status` e `clients`. Escrever isso agora é registrar a decisão no lugar onde ela não se perde.
- **Força o desenho a ser honesto.** Se `content_items` só fizesse sentido para influencer, a abstração de arquétipo único (ADR-0006) seria falsa. Preencher os campos dos três arquétipos na v1 é o teste de que a espinha é mesmo compartilhada.

**Regra de disciplina:** campo dormente **não** vira campo zumbi. Todo dormente tem uma fase declarada em que acorda. Se uma fase passa e o campo continua sem uso e sem dono, ele sai numa migração de limpeza — não fica "por via das dúvidas".

### 1.2 Identificadores em inglês, documentação em português

Tabelas, colunas, tipos e valores de ENUM são em inglês. Comentários, documentação e a interface do painel são em português.

- O código é Python com SQLAlchemy: `account.persona_card`, `task.scheduled_for`, `ContentStatus.APPROVAL_PENDING`. Misturar idiomas dentro de uma expressão (`conta.persona_card`) produz código feio e ambíguo em conversões `snake_case`/`camelCase`.
- Os serviços com que o core conversa (android-orchestrator, máquina de influencers) expõem APIs em inglês. Traduzir na fronteira do banco criaria duas nomenclaturas para a mesma coisa.
- Prompts de LLM e few-shots citam nomes de campo. Modelos são melhores em esquemas em inglês.
- O mapeamento PT ↔ EN de todo termo de domínio vive em [`docs/glossario.md`](glossario.md) — é lá que se resolve "conta" = `accounts`, "furo" = `ingested_items` com `novelty` alta, "espalhamento" = `spread_policy`.

### 1.3 Auditoria é tabela de primeira classe

`events` existe desde a linha 1 da Fase 0, antes de existir agente. Não é logging: é uma tabela transacional, com FKs para `accounts`, `campaigns` e `tasks`, escrita na **mesma transação** da decisão que ela registra.

A pergunta que o sistema precisa responder em qualquer momento é: *"por que a conta X postou isso às 19h?"*. A resposta é uma cadeia — plano do dia → intenção → draft → QA → aprovação → task → dispatch → verificação → post — e cada elo escreve um `event` com o mesmo `trace_id`. Sem isso:

- Um incidente de guardrail vira arqueologia em arquivo de log rotacionado.
- Não há como distinguir "a LLM decidiu" de "o humano mandou" de "a campanha forçou".
- Risco jurídico real (fofoca, Fase 4): publicar uma afirmação sem conseguir provar qual fonte a originou e quem aprovou é indefensável.

Como consequência, `llm_calls` também é de primeira classe: cada chamada de modelo é uma linha com custo, latência, backend e `trace_id`. Custo de LLM não é métrica de infra, é métrica de produto — decide se um agente é viável.

### 1.4 O agendamento mora no banco

Não existe fila em memória decidindo *quando* algo acontece. `tasks.scheduled_for`, `monitors.next_check_at` e `campaign_participants.slot_at` são colunas indexadas, e o dispatcher é um *tick* que faz `SELECT ... FOR UPDATE SKIP LOCKED`. Redis é usado para transporte e locks, nunca como fonte da verdade do agendamento.

Por quê:

- **Reinício não perde nada.** Derrubar a stack no meio de uma campanha de 6 horas não desagenda ninguém.
- **O agendamento é auditável e editável.** Um humano pode olhar no painel o que está agendado para as próximas 4 horas, e mover um slot com um `UPDATE`. Fila em memória não tem essa propriedade.
- **Anti-detecção depende de consulta.** `spread_policy` precisa perguntar "quantas contas da casa já agiram nesta janela?" e "esta conta já bateu o teto de ações/hora?". Isso é um `GROUP BY`, não um estado distribuído em workers.
- **Idempotência barata.** `external_task_id` + `status` no banco permitem que um webhook duplicado do orchestrator seja descartado com um `UPDATE ... WHERE status = 'dispatched'`.

O preço aceito é polling (o dispatcher acorda a cada poucos segundos) e pressão de escrita no Postgres. Para a ordem de grandeza do projeto — dezenas a algumas centenas de contas, milhares de tasks/dia — é irrelevante.

---

## 2. Mapa de relacionamentos

```
                          ┌───────────┐
                          │  clients  │ [DORMENTE — Fase 5]
                          └─────┬─────┘
                    ┌───────────┴────────────┐
                    ▼                        ▼
             ┌────────────┐            ┌───────────┐
   ┌─────────│  accounts  │            │ campaigns │
   │         └─────┬──────┘            └─────┬─────┘
   │               │ (1 conta = 1 agente)    │
   │               │                    ┌────┴──────────────────┐
   ▼               │                    ▼                       ▼
┌──────────────┐   │           ┌────────────────┐   ┌───────────────────────┐
│persona_      │   │           │ campaign_recon │   │ campaign_participants │
│versions      │   │           └───────┬────────┘   └───────────┬───────────┘
└──────────────┘   │                   │ task_id                │ account_id
                   │                   └──────────┐  ┌──────────┘
   ╔═══════════════╧════════════════╗             ▼  ▼
   ║  NARRATIVA / MEMÓRIA           ║        ┌──────────┐
   ║  ┌────────────┐                ║        │  tasks   │◄──── origin:
   ║  │ story_arcs │◄──┐            ║        └────┬─────┘  manager|self|
   ║  └────────────┘   │ arc_id     ║             │        human|campaign|
   ║  ┌────────────┐   │            ║             │        monitor
   ║  │  memories  │───┘            ║             │
   ║  └────────────┘                ║             ▼
   ║  ┌────────────┐                ║        ┌─────────┐     ┌──────────────┐
   ║  │ day_plans  │───┐            ║        │  posts  │────▶│ post_metrics │
   ║  └────────────┘   │            ║        └────┬────┘     └──────────────┘
   ╚═══════════════════╪════════════╝             │
                       │ day_plan_id              ▼
                       ▼                   ┌──────────────┐
              ┌────────────────┐           │ interactions │
              │ content_items  │──────────▶└──────────────┘
              └───────┬────────┘  (via posts)
                      │ ▲
                      │ │ content_item_id
                      │ │
   ╔══════════════════╪═╪══════════════════════════╗
   ║  INGESTÃO  [DORMENTE — Fase 4]                ║
   ║  ┌─────────┐   ┌────────────────┐   ┌───────┐ ║
   ║  │ sources │──▶│ ingested_items │◄──│monitor│ ║
   ║  └─────────┘   └───────┬────────┘   │  s    │ ║
   ║                        │            └───┬───┘ ║
   ║                        ▼                │     ║
   ║                  ┌──────────────┐◄──────┘     ║
   ║                  │ monitor_hits │─────────────╫──▶ content_items
   ║                  └──────────────┘             ║
   ╚═══════════════════════════════════════════════╝

   ┌─────────┐  compartilhado por todos os arquétipos, sem FK
   │ trends  │  (consultado no PLAN e no PRODUCE)
   └─────────┘

   ╔═══════════════════════════════════════════════════════════════╗
   ║  GOVERNANÇA — referenciam accounts/campaigns/tasks,           ║
   ║  nunca são referenciadas                                      ║
   ║  ┌───────────┐ ┌──────────────────────┐ ┌────────┐ ┌────────┐ ║
   ║  │ approvals │ │ guardrail_violations │ │ events │ │llm_call│ ║
   ║  └───────────┘ └──────────────────────┘ └────────┘ └───┬────┘ ║
   ╚═════════════════════════════════════════════════════════╪═════╝
                                    llm_call_id ◄────────────┘
                                    (day_plans, campaign_recon)

   ┌────────────────────┐
   │ schema_migrations  │  controle de versão do schema
   └────────────────────┘
```

**Leitura do mapa em uma frase:** `accounts` é o centro; tudo que é *trabalho* (conteúdo → task → post → métrica) flui da esquerda para a direita; campanhas injetam trabalho lateralmente; ingestão alimenta conteúdo por baixo; governança observa tudo por fora.

> ⚠️ O mapa acima é o da migração 0001, quando `accounts` também era a identidade. **A migração 0007 tirou a *vida* de cima do login** ([ADR-0013](adr/0013-persona-separada-da-conta.md)): memória, arcos e planos do dia pendem agora de `personas`. Leia o trecho abaixo por cima do mapa.

```
   ┌────────────┐  a IDENTIDADE: nome, slug, persona_card, persona_engine_id
   │  personas  │  existe mesmo sem login nenhum
   └─────┬──────┘
         │ persona_id (NULO é válido: coletora não tem persona)
         │
         ├───────────────┬───────────────┬───────────────┐
         ▼               ▼               ▼               ▼
   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
   │  accounts  │  │  memories  │  │ story_arcs │  │ day_plans  │
   │ os LOGINS  │  └────────────┘  └────────────┘  └────────────┘
   └─────┬──────┘        └──── a vida da personagem, uma só ────┘
         │ account_id
         ▼
   ┌────────────────────┐  ONDE cada login está rodando agora.
   │ account_placements │  Sumir daqui não apaga nada.
   └────────────────────┘

   ┌──────────────┐  observações datadas sobre conta, persona, device
   │ entity_notes │  ou servidor — polimórfica, sem FK
   └──────────────┘
```

**Três coisas, três ciclos de vida.** A personagem existe antes de qualquer login e sobrevive à perda de todos eles. O login pode ser banido e recriado. O lugar onde ele roda muda toda semana. Empilhar as três em uma linha só foi o que a 0007 desfez.

### 2.1 FKs criadas depois (ciclos)

Quatro FKs são adicionadas via `ALTER TABLE` no fim da migração porque formam ciclos de definição. Isso não é acidente, é ordenação:

| FK | De → Para | Por que fica pro fim |
|---|---|---|
| `fk_ingested_monitor` | `ingested_items.monitor_id` → `monitors.id` | `ingested_items` é declarada antes de `monitors` |
| `fk_hit_content` | `monitor_hits.content_item_id` → `content_items.id` | ingestão é declarada antes de conteúdo |
| `fk_content_campaign` | `content_items.campaign_id` → `campaigns.id` | conteúdo antes de campanha |
| `fk_recon_task` | `campaign_recon.task_id` → `tasks.id` | recon antes de tasks |
| `fk_plan_llm` / `fk_recon_llm` | `day_plans` / `campaign_recon` → `llm_calls.id` | governança é a última seção |

**Armadilha:** ao escrever uma nova migração que recria alguma dessas tabelas, lembre que a constraint tem **nome próprio** (`fk_recon_task`, não o nome gerado pelo Postgres). Um `DROP CONSTRAINT` com o nome errado falha silenciosamente em scripts com `IF EXISTS`.

---

## 3. Tabelas

Ordem: controle → tenants → contas → memória → ingestão → monitores → tendências → conteúdo → campanhas → tasks → publicações → governança → **infraestrutura** ([3.26](#326-infraestrutura-um-servidor-vários-serviços) a [3.31](#331-campos-novos-em-accounts-e-account_placements), migrações 0005/0006) → **identidade** ([3.32](#332-personas) a [3.35](#335-situação-e-presença-dois-eixos-ortogonais), migração 0007) → **identidade visual e geração** ([3.36](#336-media_assets) a [3.42](#342-remoções-e-realinhamentos-da-0008), migração 0008).

Convenções desta seção:
- Todas as colunas `id uuid` usam `DEFAULT uuid_generate_v4()`, exceto `events.id` (`bigserial`).
- `created_at`/`updated_at` são `timestamptz NOT NULL DEFAULT now()`. `updated_at` é mantido por trigger nas tabelas listadas em [3.25](#325-triggers-de-updated_at).
- "obrig." = `NOT NULL` sem default útil (precisa vir do código).

---

### 3.1 `schema_migrations`

Registro de quais migrações já rodaram neste banco. Lida e escrita apenas pelo runner de migração.

| Coluna | Tipo | Descrição |
|---|---|---|
| `version` | `text` PK | Nome do arquivo sem extensão: `0001_initial` |
| `applied_at` | `timestamptz` | Quando foi aplicada |
| `checksum` | `text` obrig. | SHA-256 do conteúdo do arquivo no momento da aplicação |

**Quando usar / armadilhas.** O `checksum` existe para detectar edição de migração já aplicada. O runner **aborta** se o hash do arquivo em disco divergir do gravado — é a defesa mecânica da regra da seção 7. Nunca "conserte" essa divergência dando `UPDATE` no checksum: ou você reverte o arquivo, ou escreve uma migração nova.

---

### 3.2 `clients` **[DORMENTE — Fase 5]**

Tenant. Existe porque clipagem é tipicamente serviço prestado a terceiros, e contas/campanhas precisarão ser atribuíveis a um contratante.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | `uuid` PK | |
| `name` | `text` obrig. | Nome do cliente/contratante |
| `contract` | `jsonb` = `{}` | Termos operacionais: volume contratado, SLA, nichos permitidos, quem aprova |
| `active` | `boolean` = `true` | Contrato vigente |
| `created_at` / `updated_at` | `timestamptz` | `updated_at` por trigger |

**Quando usar / armadilhas.** Até a Fase 5, toda linha do sistema tem `client_id IS NULL` — o "cliente" é a própria casa. **Não** escreva query que assuma `client_id NOT NULL`, e **não** use `client_id` como chave de particionamento de permissão antes da Fase 5: o modelo de autorização multi-tenant ainda não foi desenhado (`contract` é jsonb livre justamente para não congelar isso cedo).

---

### 3.3 `accounts`

**1 linha = 1 login numa plataforma.** Tudo que o Olimpo faz é atribuível a uma linha desta tabela.

> ⚠️ Até a migração 0006, a frase acima era *"1 conta = 1 agente"*, e `accounts` era também a identidade. **Não é mais.** A identidade é [`personas`](#332-personas) ([ADR-0013](adr/0013-persona-separada-da-conta.md)): uma persona pode ter até duas contas vinculadas (ver [ADR-0015](adr/0015-limite-duas-contas-por-persona.md)), e um login pode não ter persona nenhuma (as coletoras). Os campos que a 0007 acrescentou estão em [3.34](#334-campos-novos-em-accounts-migração-0007).

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | `uuid` PK | |
| `handle` | `text` obrig. | @ da conta, sem o `@` |
| `platform` | `platform` obrig. | `instagram` \| `tiktok` \| `whatsapp` |
| `archetype` | `archetype` = `influencer` | Define qual `ContentSource` o loop usa no passo SOURCE |
| `status` | `account_status` = `registered` | **Situação:** o que *nós* queremos da conta. Era `draft` até a 0007 — ver [3.35](#335-situação-e-presença-dois-eixos-ortogonais) |
| `autonomy` | `autonomy_level` = `L0` | Quanto o agente pode fazer sem humano |
| `client_id` | `uuid` → `clients` | **[DORMENTE]** `ON DELETE SET NULL` |
| ~~`persona_card`~~ | — | **[REMOVIDA na 0008]** Use [`personas.persona_card`](#332-personas) |
| ~~`persona_version`~~ | — | **[REMOVIDA na 0008]** A versão vigente é `personas.persona_version` |
| ~~`persona_engine_id`~~ | — | **[REMOVIDA na 0008]** A máquina de influencers não existe mais; a identidade visual são colunas de `personas` + `media_assets` ([3.37](#337-campos-novos-em-personas-migração-0008)) |
| ~~`device_binding`~~ | — | **[REMOVIDA na 0008]** Use `account_placements` |
| `cadence` | `jsonb` = `{"posts_per_day":1,"stories_per_day":3}` | Ritmo natural. **Teto** — campanha não pode ultrapassar |
| `timezone` | `text` = `America/Sao_Paulo` | Fuso da persona, não do servidor |
| `active_hours` | `int4range` = `[8,23)` | Janela "acordada" em horas locais. Fora dela o agente não age |
| `mood` | `jsonb` = `{}` | Estado dinâmico (humor, energia). Entra no prompt e modula tom e frequência |
| `followers` | `integer` = `0` | Último valor coletado. Usado em `campaigns.account_filter` |
| `warmup_started_at` | `timestamptz` | Início do aquecimento — base para promover `warming` → `active` |
| `last_action_at` | `timestamptz` | Última ação executada; alimenta rate limit e detecção de conta parada |
| `notes` | `text` | Anotação humana livre |
| `created_at` / `updated_at` | `timestamptz` | `updated_at` por trigger |

Restrição: `UNIQUE (platform, handle)` — o mesmo @ pode existir no Instagram e no TikTok como dois logins. Desde a 0007, os dois podem pertencer à **mesma persona**, e aí a memória é compartilhada.

> A tabela acima é a da migração 0001. Os campos de **inventário** (`external_id`, `following`, `media_count`, `jid`, `last_synced_at`, `discovered_from`) vieram na 0006 e estão em [3.31](#331-campos-novos-em-accounts-e-account_placements); os de **identidade e operação** (`persona_id`, `role`, `profile`, `secret_ref`, `labels`, `metadata`, `last_seen_in_inventory`, `previous_handles`) vieram na 0007 e estão em [3.34](#334-campos-novos-em-accounts-migração-0007). **As quatro colunas de herança saíram na 0008** — ver [3.42](#342-remoções-e-realinhamentos-da-0008).

**Quando usar / armadilhas.**
- `active_hours` é `int4range` de **horas inteiras locais**, não `timestamptz`. `[8,23)` = das 08:00 às 22:59. Range que cruza a meia-noite (ex.: madrugada de conta noturna) **não** é representável em um único range — use `[0,3)` + política no código, ou reveja a persona. Isto é uma limitação conhecida do schema v1.
- `cadence` aqui é o **teto operacional**; `persona_card.cadence` é a **intenção editorial**. Divergiram? O banco vence. O painel deve mostrar os dois.
- `mood` é jsonb sem schema fixo de propósito: o formato ainda está sendo descoberto na Fase 1/3. Não crie índice nele antes de estabilizar.
- **`device_binding` saiu na 0008.** Onde a conta vive é `account_placements` (+ `devices`, migrações 0002/0005): a mesma conta pode estar logada em vários containers, o que um jsonb escalar não representava. A 0007 marcou a coluna com `COMMENT ON COLUMN` e a 0008 a removeu.
- **`persona_card`, `persona_version` e `persona_engine_id` saíram junto.** A janela em que as colunas conviveram foi o custo declarado da [ADR-0013](adr/0013-persona-separada-da-conta.md): enquanto durou, uma consulta escrita por hábito lia o card velho e **não falhava** — devolvia dado desatualizado em silêncio. Agora falha alto, que é o comportamento desejado. Código antigo que ainda selecione essas colunas quebra na 0008, e isso é a mecânica funcionando.
- Deletar uma `account` cascateia conteúdo, posts, interações, tasks, aprovações e violações — e **não** apaga memória, arcos nem planos, que desde a 0007 pertencem à persona. **Nunca delete conta perdida — use `status = 'lost'`.** O `DELETE` existe para limpeza de ambiente de teste, e a API exige `confirm=apagar-de-verdade`.
- **Ausência de inventário não é ausência de conta.** Se todos os logins saírem dos devices, somem os `account_placements`; a conta, a persona, as observações e o histórico continuam. Ver [3.35](#335-situação-e-presença-dois-eixos-ortogonais).

---

### 3.4 `persona_versions`

Histórico imutável do Persona Card. Responde "por que ela mudou de voz na semana passada?".

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | `uuid` PK | |
| `account_id` | `uuid` → `accounts` obrig. | `ON DELETE CASCADE`. **[HERANÇA desde a 0008]** |
| `persona_id` | `uuid` → `personas` | `ON DELETE CASCADE`. **Coluna da 0008** — o histórico do card pertence à personagem |
| `version` | `integer` obrig. | Inteiro monotônico por conta |
| `persona_card` | `jsonb` obrig. | Snapshot **completo** do card nessa versão (não é diff) |
| `changed_by` | `text` | `human:chris` \| `agent:reflect` \| `migration:0007` |
| `change_note` | `text` | Justificativa em texto livre — obrigatória por convenção do painel |
| `created_at` | `timestamptz` | |

Restrição: `UNIQUE (account_id, version)`.

**Quando usar / armadilhas.** Grave a versão **antes** de sobrescrever o card, na mesma transação. Snapshot completo é escolha consciente: diffs economizam bytes e custam a capacidade de reconstruir o prompt exato de um post antigo. Nunca faça `UPDATE` em uma linha aqui — é append-only.

> ✅ **A dívida da 0007 foi paga na 0008.** Enquanto a tabela era chaveada só por `account_id`, uma persona com três logins gerava três linhas por bump, com o mesmo `version` e o mesmo snapshot — funcionava, era auditável e era modelagem torta. A 0008 acrescentou `persona_id` e fez o backfill a partir de `accounts.persona_id`:
>
> ```sql
> UPDATE persona_versions pv
>    SET persona_id = a.persona_id
>   FROM accounts a
>  WHERE a.id = pv.account_id AND a.persona_id IS NOT NULL;
> ```
>
> O índice novo é `idx_persona_versions_persona (persona_id, version DESC)`, e é por ele que o histórico deve ser lido. `account_id` continua na tabela como herança: as linhas antigas dependem dele, e a `UNIQUE (account_id, version)` ainda vale. ❓ Linhas cuja conta de origem já tinha sido desvinculada (`persona_id IS NULL`) ficaram sem `persona_id` — o backfill não tinha de onde tirar o dono.

---

### 3.5 `story_arcs`

Arco narrativo em curso ("treinando para a maratona", "mudança de cidade"). É o que impede a conta de virar um gerador de posts sem continuidade.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | `uuid` PK | |
| `account_id` | `uuid` → `accounts` obrig. | `ON DELETE CASCADE`. **[HERANÇA desde a 0007]** — o arco é da personagem |
| `persona_id` | `uuid` → `personas` | `ON DELETE CASCADE`. Coluna da 0007; é por aqui que se lê |
| `title` | `text` obrig. | Nome curto do arco |
| `summary` | `text` obrig. | Sinopse injetada no prompt de PLAN |
| `state` | `jsonb` = `{}` | Onde está no arco: fase, marcos batidos, próximos beats |
| `starts_at` | `date` obrig. | |
| `ends_at` | `date` | `NULL` = arco aberto |
| `active` | `boolean` = `true` | |
| `created_at` / `updated_at` | `timestamptz` | `updated_at` por trigger |

**Quando usar / armadilhas.** Nada impede vários arcos ativos por persona — e isso é intencional (um arco pessoal + um profissional). Mas **mais de 2–3 arcos ativos degradam o plano do dia**: o prompt fica com objetivos conflitantes e a LLM produz posts genéricos. Trate `count(*) WHERE active` > 3 como alerta operacional. Encerrar arco é `active = false` + `ends_at`, nunca `DELETE` (memórias apontam para ele).

Desde a 0007, `account_id` e `persona_id` coexistem: a coluna antiga é herança, e o índice novo é `idx_arcs_persona` (parcial em `active`). Um arco escrito só com `account_id` some da leitura por persona — preencha `persona_id` sempre.

---

### 3.6 `memories`

O *memory stream* do blueprint generative_agents. Tudo que o agente sabe sobre si e sobre o mundo dele.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | `uuid` PK | |
| `account_id` | `uuid` → `accounts` obrig. | `ON DELETE CASCADE`. **[HERANÇA desde a 0007]** |
| `persona_id` | `uuid` → `personas` | `ON DELETE CASCADE`. Coluna da 0007 — **a memória é da personagem, não do login** |
| `kind` | `memory_kind` obrig. | `episodic` \| `semantic` \| `narrative` |
| `content` | `text` obrig. | A memória em linguagem natural, primeira pessoa |
| `embedding` | `vector(1024)` | Embedding de `content`. `NULL` = ainda não indexada |
| `importance` | `real` = `5.0` | 0..10, atribuída pela LLM **na escrita** |
| `metadata` | `jsonb` = `{}` | Refs: post_id, handle do seguidor, task_id, fonte |
| `arc_id` | `uuid` → `story_arcs` | `ON DELETE SET NULL` |
| `occurred_at` | `timestamptz` = `now()` | Quando o fato aconteceu (≠ quando foi gravado) |
| `last_used_at` | `timestamptz` | Última vez que foi recuperada para um prompt |
| `created_at` | `timestamptz` | Quando foi gravada |

**Quando usar / armadilhas.**
- `vector(1024)` fixa a dimensão do modelo de embedding. **Trocar de modelo de embedding exige migração e re-embedding de tudo** — não é configuração, é decisão de schema. Modelo escolhido e sua dimensão devem estar registrados em [docs/09](09-llm-gateway.md).
- `occurred_at` vs `created_at`: uma reflexão escrita à noite sobre a manhã tem `occurred_at` de manhã. A recência da recuperação usa `occurred_at`. Confundir os dois faz o agente achar que tudo aconteceu na hora da reflexão.
- `importance` é atribuída **uma vez**, na escrita, pela LLM que criou a memória. Não recalcule em lote: isso reescreve a história do agente.
- `last_used_at` não participa do ranking na v1 — é telemet…25851 tokens truncated… dá recall alto com latência baixa; custa mais na escrita e mais RAM que IVFFlat. Escolhido porque memória é lida muito mais do que escrita |
| `idx_content_account_status` | `(account_id, status)` | Painel da conta: "o que a Nina tem em cada estágio" |
| `idx_campaigns_status` | `(status)` | Lista de campanhas por estado; alimenta o monitor de campanhas travadas |
| `idx_recon_campaign` | `(campaign_id)` | Recon de uma campanha (lembrar: pegar o mais recente) |
| `idx_tasks_account` | `(account_id, created_at DESC)` | Histórico de ações da conta; base do cálculo de rate limit por hora |
| `idx_posts_account` | `(account_id, published_at DESC)` | Feed da conta no painel; "último post foi quando?" |
| `idx_metrics_post` | `(post_id, collected_at DESC)` | Métrica mais recente de um post (`DISTINCT ON`) e série temporal |
| `idx_monitor_hits_monitor` | `(monitor_id, detected_at DESC)` | Depuração de `trigger_rules`: os últimos hits de um monitor |
| `idx_violations_recent` | `(created_at DESC)` | Mural de incidentes: "o que deu errado nas últimas 24h" em toda a frota |
| `idx_events_account` | `(account_id, created_at DESC)` | Linha do tempo de uma conta |
| `idx_events_type` | `(type, created_at DESC)` | Séries por tipo de evento (taxa de `content.qa_failed`/dia) |
| `idx_events_trace` | `(trace_id)` | **Reconstruir uma decisão inteira.** É o índice que faz a auditoria ser consulta e não investigação |
| `idx_llm_calls_time` | `(created_at DESC)` | Agregação de custo/latência por janela |

### 5.3 Unicidades como regra de negócio

| Constraint | O que impede |
|---|---|
| `accounts (platform, handle)` | Duas linhas para a mesma conta real — dois agentes brigando pelo mesmo device |
| `personas (slug)` | Duas identidades com o mesmo identificador legível. É por ele que se fala da personagem fora do banco |
| `persona_versions (account_id, version)` | Duas versões com o mesmo número; garante linha do tempo íntegra |
| `day_plans (account_id, plan_date)` | Planejar o mesmo dia duas vezes (idempotência do PLAN) |
| `sources (kind, endpoint)` | Cadastrar a mesma fonte duas vezes e dobrar a coleta |
| `ingested_items (dedup_hash)` | Reprocessar o mesmo furo |
| `campaign_participants (campaign_id, account_id)` | Mesma conta agir duas vezes na mesma campanha — padrão que denuncia automação |

### 5.4 Faltas conhecidas

Registradas aqui para não serem redescobertas como bug:

- **Sem `UNIQUE (platform, external_id)` em `posts`** — reentrega de webhook pode duplicar. Guarda hoje é no código.
- **Sem índice em `approvals (subject_type, subject_id)`** — buscar "as aprovações deste conteúdo" faz seq scan. Aceitável enquanto a tabela é pequena; adicionar quando passar de ~10⁵ linhas.
- **Sem índice em `guardrail_violations (account_id, created_at DESC)`** — a query "violações desta conta" usa `idx_violations_recent` e filtra. Revisar quando a frota crescer.
- **Sem índice em `content_items (campaign_id)`** — "conteúdo desta campanha" é seq scan.
- **`llm_calls` sem índice em `trace_id`** — correlacionar chamada de LLM com evento por trace hoje é scan. Candidato imediato quando a auditoria virar rotina.
- **A presença não é indexável hoje** ([3.35](#335-situação-e-presença-dois-eixos-ortogonais)). Filtrar por `presence` avalia o `CASE` linha a linha, com subconsultas em `account_placements`. Aceitável na escala atual porque a listagem é paginada; se doer, a saída é materializar a presença numa coluna atualizada pela varredura — ao custo de ela deixar de ser sempre atual.

---

### 5.5 Índices da identidade e da busca em massa (migração 0007)

Todos existem por causa da escala: a operação real tem **milhares** de logins, e a tela de contas é varrida, filtrada e ordenada o dia inteiro.

| Índice | Definição | Consulta que serve |
|---|---|---|
| `idx_accounts_persona` | `(persona_id)` | "Quais logins são desta personagem?" — a ficha de persona e o `LEFT JOIN personas` da listagem |
| `idx_accounts_labels` | gin em `(labels)` | Filtro por rótulo (`:label = ANY(labels)`). Rótulo é o eixo que o operador inventa sozinho, e é o que sustenta a ação em lote |
| `idx_accounts_handle_trgm` | gin `(handle gin_trgm_ops)` | **Busca "contém"** — `handle ILIKE '%luna%'`. É o que o operador digita, e sem trigrama é seq scan a cada tecla |
| `idx_personas_active` | `(name) WHERE active` | Lista de personas em ordem alfabética, sem as aposentadas |
| `idx_personas_labels` | gin em `(labels)` | Idem `accounts`, do lado da identidade |
| `idx_memories_persona` | `(persona_id, kind, occurred_at DESC)` | Recuperação de memória por recência dentro de um tipo, agora **por personagem** |
| `idx_arcs_persona` | `(persona_id) WHERE active` | Contexto do PLAN: arcos vivos da personagem |
| `idx_notes_subject` | `(subject_type, subject_id, created_at DESC)` | Observações de uma entidade, mais recentes primeiro |
| `idx_notes_pinned` | `(subject_type, subject_id) WHERE pinned` | As fixadas, que a ficha mostra no topo antes de tudo |

**Por que trigrama e não `LIKE 'prefixo%'`.** Índice B-tree serve busca por prefixo; o operador não digita prefixo, digita pedaço — lembra "luna" de `@lunaprado.oficial`. `pg_trgm` é a extensão já habilitada para dedup e QA de caption, então o custo marginal é um índice, não uma dependência nova.

**As facetas não têm índice próprio, e é de propósito.** As contagens por plataforma, situação, papel, arquétipo e presença varrem `accounts` inteira — mas em **uma única consulta** com todas as agregações, em vez de seis idas ao banco. Índice de contagem só ajudaria com `count` por coluna isolada; o gargalo, se aparecer, é a passada única e se resolve com cache curto.

### 5.6 Índices da mídia e da geração (migração 0008)

| Índice | Definição | Consulta que serve |
|---|---|---|
| `idx_media_persona` | `(persona_id, created_at DESC)` | A galeria da ficha da persona — o conteúdo produzido, mais recente primeiro |
| `idx_media_role` | `(persona_id, role)` | As quatro âncoras de identidade, e os figurinos de uma persona |
| `idx_media_kind` | `(kind, created_at DESC)` | Biblioteca global filtrada por tipo |
| `idx_media_hash` | **UNIQUE** `(content_hash) WHERE content_hash IS NOT NULL` | **Dedupe.** O parcial é o que permite reexecutar o importador sem conflito em linhas sem hash |
| `idx_personas_niches` | gin em `(niches)` | "Quais personas atendem este nicho?" — seleção para campanha e para o pool de cenas |
| `idx_wardrobe_persona` | `(persona_id, sort_order)` | A gaveta de figurinos, na ordem que o operador definiu |
| `idx_brands_persona` | `(persona_id)` | Marcas exclusivas de uma persona |
| `idx_brands_catalogo` | `(name) WHERE persona_id IS NULL` | **O catálogo geral** — a consulta mais frequente da tela de produto |
| `idx_genjobs_pendentes` | `(next_poll_at) WHERE status IN ('queued','running')` | O poller da fila. Parcial pela mesma razão de `idx_tasks_due`: o histórico terminal não entra |
| `idx_genjobs_persona` | `(persona_id, created_at DESC)` | Histórico de geração de uma personagem |
| `idx_drafts_persona` | `(persona_id, created_at DESC)` | Rascunhos de vídeo pendentes |

**Dois índices parciais carregam o peso.** `idx_media_hash` transforma dedupe em restrição de banco, não em disciplina de código — o mesmo arquivo simplesmente não entra duas vezes, e o importador é idempotente de graça. `idx_genjobs_pendentes` mantém o poller barato indefinidamente: um ano de jobs `done` não torna a varredura mais lenta em nada.

---

## 6. Consultas de referência

Consultas testadas contra o schema da migração 0001. Servem de base para o código e para depuração via `make psql`.

### 6.1 Tasks vencidas prontas para dispatch (o tick do dispatcher)

Respeita janela, prioridade, expiração, `active_hours` da conta no fuso dela, e kill switch por status. `SKIP LOCKED` permite N workers sem coordenação externa.

```sql
WITH claimable AS (
    SELECT t.id
    FROM tasks t
    JOIN accounts a ON a.id = t.account_id
    WHERE t.status IN ('pending', 'scheduled')
      AND t.scheduled_for <= now()
      AND (t.expires_at IS NULL OR t.expires_at > now())
      AND t.attempts < t.max_attempts
      AND a.status = 'active'
      -- só age dentro da janela "acordada", na hora local da persona
      AND EXTRACT(HOUR FROM now() AT TIME ZONE a.timezone)::int
          <@ a.active_hours
    ORDER BY t.priority ASC, t.scheduled_for ASC
    LIMIT 50
    FOR UPDATE OF t SKIP LOCKED
)
UPDATE tasks t
   SET status        = 'dispatched',
       dispatched_at = now(),
       attempts      = t.attempts + 1
  FROM claimable c
 WHERE t.id = c.id
RETURNING t.id, t.account_id, t.type, t.payload, t.campaign_id, t.content_item_id;
```

> `idx_tasks_due` serve o `WHERE`+`ORDER BY`. O `JOIN` com `accounts` usa a PK. O `LIMIT 50` é o tamanho do lote por tick — ajuste com `WORKER_CONCURRENCY`.

### 6.2 Fila de aprovação pendente

Une as três origens de aprovação (conteúdo, campanha, interação) em uma fila só, com idade e tipo de revisão.

```sql
-- Conteúdo aguardando decisão humana
SELECT
    'content_item'                          AS subject_type,
    ci.id                                   AS subject_id,
    a.handle,
    a.archetype,
    a.autonomy,
    ci.kind::text                           AS item_kind,
    left(ci.caption, 120)                   AS preview,
    ci.rights_status,
    ci.claim_status,
    ci.scheduled_for,
    ci.created_at                           AS requested_at,
    now() - ci.created_at                   AS idade,
    ap.sampled
FROM content_items ci
JOIN accounts a         ON a.id = ci.account_id
LEFT JOIN approvals ap  ON ap.subject_type = 'content_item'
                       AND ap.subject_id  = ci.id
                       AND ap.decided_at IS NULL
WHERE ci.status = 'approval_pending'

UNION ALL

-- Interações pendentes de resposta que exigem humano
SELECT
    'interaction', i.id, a.handle, a.archetype, a.autonomy,
    i.kind, left(i.body, 120),
    NULL, NULL, NULL,
    i.received_at, now() - i.received_at,
    false
FROM interactions i
JOIN accounts a ON a.id = i.account_id
WHERE i.replied_at IS NULL
  AND (i.sensitive                       -- sensível nunca é auto-respondido
       OR a.autonomy IN ('L0', 'L1'))    -- L0/L1 mandam tudo para revisão

UNION ALL

-- Campanhas aguardando aval
SELECT
    'campaign', c.id, NULL, NULL, NULL,
    c.kind::text, left(c.brief, 120),
    NULL, NULL, c.window_start,
    c.updated_at, now() - c.updated_at, false
FROM campaigns c
WHERE c.status = 'approval_pending'

ORDER BY idade DESC;
```

> Serve-se de `idx_content_pending_approval`, `idx_interactions_pending` e `idx_campaigns_status`. Ordenar por idade descrescente coloca o que está apodrecendo na fila no topo — é o que evita furo perdido por revisão esquecida.

### 6.3 Recuperação de memória (similaridade × recência × importância)

A fórmula do generative_agents, com os três eixos normalizados em 0..1 e somados com pesos. Recência é decaimento exponencial sobre `occurred_at`.

```sql
-- $1 = account_id
-- $2 = embedding da consulta (vector(1024))
-- $3 = meia-vida da recência em horas (ex.: 72)
-- $4 = quantas memórias devolver (ex.: 12)
WITH scored AS (
    SELECT
        m.id,
        m.kind,
        m.content,
        m.importance,
        m.occurred_at,
        -- 1) RELEVÂNCIA: 1 - distância de cosseno  →  0..1
        (1 - (m.embedding <=> $2::vector))                       AS relevance,
        -- 2) RECÊNCIA: decaimento exponencial, meia-vida $3 horas → 0..1
        exp(
            -ln(2) * (EXTRACT(EPOCH FROM now() - m.occurred_at) / 3600.0) / $3
        )                                                        AS recency,
        -- 3) IMPORTÂNCIA: escala 0..10 atribuída pela LLM  →  0..1
        (m.importance / 10.0)                                    AS importance_norm
    FROM memories m
    WHERE m.account_id = $1              -- NUNCA remover: isolamento entre agentes
      AND m.embedding IS NOT NULL
    ORDER BY m.embedding <=> $2::vector  -- usa o índice HNSW
    LIMIT 200                            -- pré-filtro: top-200 por similaridade
)
SELECT
    id, kind, content, importance, occurred_at,
    round(relevance::numeric, 4)       AS relevance,
    round(recency::numeric, 4)         AS recency,
    round(importance_norm::numeric, 4) AS importance_norm,
    round((1.0 * relevance + 1.0 * recency + 1.0 * importance_norm)::numeric, 4)
        AS score
FROM scored
ORDER BY score DESC
LIMIT $4;
```

**Notas de implementação.**
- Os pesos `1.0 / 1.0 / 1.0` são os do paper. Ajuste por arquétipo: fofoca quer recência dominante (`0.7 / 2.0 / 0.5`); influencer quer narrativa (`1.0 / 0.8 / 1.5`).
- O `LIMIT 200` interno é o que permite usar o índice HNSW: o ranking completo é calculado só sobre os candidatos mais similares. Sem ele, a query vira seq scan com aritmética em toda a tabela.
- `<=>` é distância de cosseno (0 = idêntico). Por isso `1 - distância`.
- Depois de usar as memórias no prompt, marque-as:
  ```sql
  UPDATE memories SET last_used_at = now() WHERE id = ANY($1::uuid[]);
  ```

### 6.4 Reconstruir a história de um post (`events` + `trace_id`)

Do plano do dia à publicação verificada, incluindo cada chamada de LLM e cada intervenção humana.

```sql
-- $1 = posts.id
WITH alvo AS (
    SELECT p.id AS post_id, p.task_id, p.content_item_id, p.account_id
    FROM posts p WHERE p.id = $1
),
-- o trace_id nasce no PLAN e é propagado; pegamos por qualquer elo conhecido
traces AS (
    SELECT DISTINCT e.trace_id
    FROM events e, alvo t
    WHERE e.trace_id IS NOT NULL
      AND (e.task_id = t.task_id OR e.detail->>'content_item_id' = t.content_item_id::text)
)
SELECT * FROM (
    SELECT e.created_at, 'event'    AS fonte, e.type       AS rotulo,
           e.detail                 AS detalhe, e.trace_id
    FROM events e JOIN traces tr ON tr.trace_id = e.trace_id

    UNION ALL

    SELECT l.created_at, 'llm_call',
           l.purpose || ' @ ' || l.backend || '/' || l.model,
           jsonb_build_object('tokens_in',  l.prompt_tokens,
                              'tokens_out', l.output_tokens,
                              'latency_ms', l.latency_ms,
                              'cost_usd',   l.cost_usd,
                              'success',    l.success,
                              'error',      l.error),
           l.trace_id
    FROM llm_calls l JOIN traces tr ON tr.trace_id = l.trace_id

    UNION ALL

    SELECT ap.decided_at, 'approval',
           ap.subject_type || ' → ' || coalesce(ap.decision, 'pendente'),
           jsonb_build_object('by', ap.decided_by, 'note', ap.note,
                              'sampled', ap.sampled),
           NULL
    FROM approvals ap, alvo t
    WHERE ap.subject_id IN (t.content_item_id, t.post_id)

    UNION ALL

    SELECT gv.created_at, 'guardrail',
           gv.rule || ' [' || gv.severity || ']',
           gv.detail, NULL
    FROM guardrail_violations gv, alvo t
    WHERE gv.subject_id IN (t.content_item_id, t.post_id, t.task_id)
) linha_do_tempo
WHERE created_at IS NOT NULL
ORDER BY created_at;
```

> Usa `idx_events_trace`. **É esta consulta que justifica a disciplina de propagar `trace_id`** — se o trace se perde entre o PLAN e o dispatch, a história aparece cortada ao meio. Considere adicionar índice em `llm_calls(trace_id)` (ver [5.4](#54-faltas-conhecidas)).

### 6.5 Custo de LLM por dia e por backend

```sql
SELECT
    date_trunc('day', created_at AT TIME ZONE 'America/Sao_Paulo')::date AS dia,
    backend,
    count(*)                                            AS chamadas,
    count(*) FILTER (WHERE NOT success)                 AS falhas,
    sum(prompt_tokens)                                  AS tokens_entrada,
    sum(output_tokens)                                  AS tokens_saida,
    round(avg(latency_ms))                              AS latencia_media_ms,
    percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) AS latencia_p95_ms,
    round(sum(cost_usd), 4)                             AS custo_usd
FROM llm_calls
WHERE created_at >= now() - interval '30 days'
GROUP BY ROLLUP (dia, backend)
ORDER BY dia DESC NULLS LAST, custo_usd DESC NULLS LAST;
```

Variante operacional — **quanto já gastamos hoje em API externa** (compare com `LLM_DAILY_BUDGET_USD`):

```sql
SELECT
    round(sum(cost_usd), 4) AS gasto_hoje_usd,
    count(*)                AS chamadas_externas
FROM llm_calls
WHERE backend NOT LIKE 'mac_mini%'
  AND created_at >= date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo');
```

E **onde o dinheiro está indo**, por propósito e por conta:

```sql
SELECT a.handle, l.purpose, count(*) AS chamadas, round(sum(l.cost_usd), 4) AS usd
FROM llm_calls l
LEFT JOIN accounts a ON a.id = l.account_id
WHERE l.created_at >= now() - interval '7 days'
GROUP BY 1, 2
HAVING sum(l.cost_usd) > 0
ORDER BY usd DESC
LIMIT 25;
```

> `idx_llm_calls_time` serve todas as três.

### 6.6 Contas que passaram do teto de ações/hora

Só a família de **execução** conta (produção e coleta local não tocam device). Teto default: `ACCOUNT_MAX_ACTIONS_PER_HOUR = 12`.

```sql
-- $1 = teto de ações/hora (ex.: 12)
WITH acoes AS (
    SELECT
        t.account_id,
        date_trunc('hour', coalesce(t.verified_at, t.dispatched_at)) AS hora,
        count(*) AS n
    FROM tasks t
    WHERE t.type IN (
            'publish_post','publish_story','publish_reels',
            'like','comment','follow','unfollow','save','share',
            'watch_reels','view_stories','send_dm','reply_comment')
      AND t.status IN ('dispatched','running','verified')
      AND coalesce(t.verified_at, t.dispatched_at) >= now() - interval '24 hours'
    GROUP BY 1, 2
)
SELECT
    a.handle, a.platform, a.archetype, a.autonomy,
    ac.hora, ac.n AS acoes_na_hora, $1 AS teto,
    ac.n - $1 AS excedente
FROM acoes ac
JOIN accounts a ON a.id = ac.account_id
WHERE ac.n > $1
ORDER BY excedente DESC, ac.hora DESC;
```

Versão **preventiva**, a ser chamada pelo dispatcher antes de despachar (janela deslizante de 60 min, não hora cheia):

```sql
-- $1 = account_id ; $2 = teto
SELECT count(*) >= $2 AS estourou
FROM tasks
WHERE account_id = $1
  AND type NOT IN ('plan_day','produce_content','reflect')
  AND status IN ('dispatched','running','verified')
  AND coalesce(dispatched_at, created_at) > now() - interval '1 hour';
```

> A versão de hora cheia é **relatório**; a de janela deslizante é **guardrail**. Um farm detectado por rajada de 12 ações em 4 minutos passa ileso pela primeira e é barrado pela segunda.

### 6.7 Campanhas aguardando recon

```sql
SELECT
    c.id,
    c.name,
    c.kind,
    c.status,
    c.target_handle,
    c.target_url,
    c.window_start,
    now() - c.updated_at                     AS parada_ha,
    -- há task de recon? em que estado?
    t.id                                     AS recon_task_id,
    t.status                                 AS recon_task_status,
    t.attempts,
    t.last_error,
    -- há recon já gravado?
    r.captured_at,
    r.analyzed_at,
    r.safety_verdict,
    CASE
        WHEN t.id IS NULL                        THEN 'sem task de recon — criar'
        WHEN t.status = 'failed'                 THEN 'recon falhou — ver last_error'
        WHEN t.status = 'expired'                THEN 'recon expirou — realvo?'
        WHEN r.captured_at IS NULL               THEN 'aguardando captura no device'
        WHEN r.analyzed_at IS NULL               THEN 'capturado, aguardando LLM'
        WHEN r.safety_verdict = 'blocked'        THEN 'BLOQUEADO — abortar campanha'
        ELSE                                          'pronto para planning'
    END                                      AS diagnostico
FROM campaigns c
LEFT JOIN LATERAL (
    SELECT * FROM tasks
    WHERE campaign_id = c.id AND type = 'extract_content'
    ORDER BY created_at DESC LIMIT 1
) t ON true
LEFT JOIN LATERAL (
    SELECT * FROM campaign_recon
    WHERE campaign_id = c.id
    ORDER BY created_at DESC LIMIT 1
) r ON true
WHERE c.status = 'recon_pending'
ORDER BY c.window_start ASC;
```

> Os dois `LATERAL ... ORDER BY created_at DESC LIMIT 1` são a forma correta de pegar "o recon/task mais recente" — lembre que não há `UNIQUE (campaign_id)` em `campaign_recon` ([3.15](#315-campaign_recon)). Campanha em `recon_pending` com `window_start` no passado é incidente: a janela está queimando sem que nada tenha sido planejado.

---

## 7. Convenções de migração

### 7.1 SQL puro, versionado

Sem Alembic, sem autogeração. As migrações são arquivos `.sql` em [`db/migrations/`](../db/migrations/), aplicados em ordem lexicográfica por um runner simples (`make migrate`), que registra cada aplicação em `schema_migrations`.

Por que SQL puro:

- **O schema é o documento.** Alguém que abre `0001_initial.sql` lê o modelo inteiro, com comentários em português explicando *por que* cada campo existe. Um autogenerador produziria `op.add_column(...)` sem contexto.
- **Índices parciais, HNSW, `int4range`, `CHECK`, triggers em `DO $$` — nada disso sobrevive bem a autogeração.** Metade do valor do nosso schema está exatamente nesses detalhes.
- **Revisão de PR é leitura de SQL**, não de diff de modelo Python. É onde um `DROP COLUMN` acidental é pego.
- **Zero dependência de framework de migração** — coerente com a ADR-0001 (core fino).

Custo aceito: escrevemos o `UP` à mão e não temos `DOWN` automático (ver 7.4).

### 7.2 Nomenclatura

```
NNNN_descricao_curta.sql
```

- `NNNN` — quatro dígitos, sequencial, **sem buracos**: `0001`, `0002`, `0003`.
- `descricao_curta` — `snake_case`, em **português**, no infinitivo ou como substantivo do que a migração faz. Consistente com "documentação em português, identificadores em inglês": o nome do arquivo é documentação.
- Sem timestamp no nome. Ordem sequencial explícita evita o clássico "duas branches criaram `20260805_x`" com ordem de aplicação ambígua.

Exemplos válidos:

```
0001_initial.sql
0002_indice_llm_calls_trace.sql
0003_check_kind_content_items.sql
0004_particiona_post_metrics.sql
0005_acorda_ingestao_fase4.sql
```

**Colisão de número** entre branches: quem faz merge por último renumera. É trabalho manual de 30 segundos e é o preço de ter ordem determinística.

### 7.3 Nunca edite migração já aplicada

**Regra absoluta.** Migração aplicada em qualquer ambiente compartilhado (staging, produção — e, na prática, no banco do colega) é imutável.

Mecanismo de defesa: o runner grava `schema_migrations.checksum` (SHA-256 do arquivo) e **compara a cada execução**. Divergência = falha imediata com a lista de arquivos alterados. Não existe flag para ignorar.

Por quê:
- O banco já foi transformado. Editar o arquivo não desfaz o `ALTER TABLE` que rodou ontem — só cria a ilusão de que o histórico é outro.
- Ambientes divergem em silêncio: o seu banco tem a coluna, o de produção não, e o SQL parece o mesmo nos dois lugares.
- A trilha de auditoria do schema morre — e este é um projeto cujo princípio nº 3 é auditoria.

**O que fazer em vez disso:**

| Situação | Ação |
|---|---|
| Erro de digitação em migração já aplicada | Nova migração corrigindo |
| Coluna que não deveria existir | Nova migração com `DROP COLUMN` (e prazo de carência, ver 7.5) |
| Migração ainda **não** aplicada em lugar nenhum, nem no seu banco local, nem em branch de outra pessoa | Pode editar. Este é o único caso |
| Migração aplicada só no seu local, mas já **enviada** | Trate como imutável: outra pessoa pode ter rodado |

### 7.4 Estrutura de um arquivo de migração

```sql
-- =============================================================================
-- Olimpo — Migração 0002: índice de trace em llm_calls
-- =============================================================================
-- Motivo: a consulta de auditoria (docs/02 § 6.4) faz seq scan em llm_calls
-- ao correlacionar por trace_id. Com ~40k chamadas/dia isso já custa ~800ms.
--
-- Reversão: DROP INDEX CONCURRENTLY idx_llm_calls_trace;
-- =============================================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_llm_calls_trace
    ON llm_calls(trace_id) WHERE trace_id IS NOT NULL;
```

Convenções de conteúdo:

1. **Cabeçalho obrigatório** com número, título, *motivo* e como reverter. O motivo é o que faz a migração ser legível daqui a um ano.
2. **Uma migração = uma mudança coerente.** Não junte "adiciona coluna de fofoca" com "corrige índice de tasks".
3. **`IF NOT EXISTS` / `IF EXISTS`** sempre que possível — torna a reaplicação inofensiva.
4. **Idempotência onde der.** O runner protege com `schema_migrations`, mas migração idempotente sobrevive a intervenção manual atrapalhada.
5. **Sem `DOWN` automático.** Reversão é descrita em comentário e, quando realmente necessária, escrita como uma migração nova (`0009_reverte_0008.sql`). Downgrade automático em produção com dados é ilusão de segurança.
6. **DDL pesada fora de transação.** `CREATE INDEX CONCURRENTLY` e `ALTER TYPE ... ADD VALUE` não rodam dentro de bloco transacional; sinalize no cabeçalho para o runner não envolver o arquivo em `BEGIN/COMMIT`.
7. **Migração de dados vai em arquivo separado** da migração de schema, com `LIMIT`/lote quando a tabela for grande.

### 7.5 Mudanças perigosas: o padrão em três passos

Para qualquer mudança que possa quebrar código em execução (renomear, remover, apertar `NOT NULL`), use expansão → migração → contração, em **três migrações separadas** e três deploys:

| Passo | Migração | Deploy |
|---|---|---|
| **Expandir** | Cria a nova coluna, nullable, com default | Código passa a escrever nos **dois** lugares |
| **Migrar** | Backfill em lotes | Código passa a ler do novo |
| **Contrair** | `DROP` do antigo, aplica `NOT NULL` | Código para de escrever no antigo |

Nunca faça `ALTER TABLE ... RENAME COLUMN` em uma tacada: entre o `COMMIT` e o deploy do código novo existe uma janela em que a aplicação está quebrada.

Casos específicos deste schema:

- **`ALTER TYPE ... ADD VALUE`** (novo valor de ENUM) não é transacional e não é revertível. Adicione o valor numa migração isolada, faça deploy, e só então use o valor.
- **Trocar a dimensão de `memories.embedding`** exige recriar a coluna e re-embeddar toda a memória. Trate como projeto, não como migração ([3.6](#36-memories)).
- **Novo campo mutável** exige adicionar o trigger `touch_updated_at` na mesma migração se a tabela for nova ([3.25](#325-triggers-de-updated_at)).

### 7.6 Checklist de revisão de migração

- [ ] O número é o próximo da sequência, sem buraco e sem colisão.
- [ ] O cabeçalho diz **por que**, não só o quê.
- [ ] Nenhum arquivo já aplicado foi tocado (o checksum confirma).
- [ ] Coluna nova ou tabela nova está documentada em `docs/02` (esta página) na mesma PR.
- [ ] Se dormente, está marcada `[DORMENTE]` **com a fase em que acorda**.
- [ ] Índice novo tem uma consulta real que o justifica — se possível, com `EXPLAIN` antes/depois no corpo da PR.
- [ ] `DROP`/`NOT NULL`/`RENAME` seguem o padrão de três passos ([7.5](#75-mudanças-perigosas-o-padrão-em-três-passos)).
- [ ] Tabela nova e mutável ganhou o trigger de `updated_at`.
- [ ] Rodou em banco limpo (`make reset && make migrate`) **e** em cópia de banco com dados.

---

## Ver também

- [`db/migrations/0001_initial.sql`](../db/migrations/0001_initial.sql) — a fonte da verdade do núcleo
- [`db/migrations/0005_servers_and_services.sql`](../db/migrations/0005_servers_and_services.sql) · [`0006_account_inventory.sql`](../db/migrations/0006_account_inventory.sql) — infraestrutura e inventário ([3.26](#326-infraestrutura-um-servidor-vários-serviços))
- [`db/migrations/0007_personas_e_contas.sql`](../db/migrations/0007_personas_e_contas.sql) — personas, papéis, observações e presença ([3.32](#332-personas) a [3.35](#335-situação-e-presença-dois-eixos-ortogonais))
- [`db/migrations/0008_absorve_maquina_de_influencers.sql`](../db/migrations/0008_absorve_maquina_de_influencers.sql) — mídia, identidade visual, guarda-roupa, marcas e fila de geração ([3.36](#336-media_assets) a [3.42](#342-remoções-e-realinhamentos-da-0008))
- [ADR-0001](adr/0001-core-proprio.md) — por que core próprio; por que o modelo de dados é nosso
- [ADR-0012](adr/0012-servidor-com-varios-servicos.md) — por que servidor e serviço são tabelas diferentes
- [ADR-0013](adr/0013-persona-separada-da-conta.md) — por que a identidade, o login e o lugar onde ele roda são três coisas
- [ADR-0014](adr/0014-absorver-a-maquina-de-influencers.md) — por que a máquina de influencers deixou de existir e a identidade visual virou coluna
- [docs/13 — Geração de mídia](13-geracao-de-midia.md) — o subsistema que escreve em `media_assets` e `generation_jobs`
- [docs/14 — Motores de prompt](14-motores-de-prompt.md) — quais colunas de `personas` o motor lê a cada geração
- [docs/contratos/android-manager.md](contratos/android-manager.md) — o serviço que alimenta `devices`
- [docs/04 — Persona Card](04-persona-card-spec.md) — o schema de `personas.persona_card`
- [docs/05 — Loop do agente](05-loop-do-agente.md) — quem escreve em qual tabela, em qual passo
- [docs/06 — Campanhas](06-campanhas.md) — `spread_policy`, recon e espalhamento
- [docs/08 — Guardrails e autonomia](08-guardrails-e-autonomia.md) — catálogo de `rule` e política por nível
- [docs/11 — Observabilidade](11-observabilidade.md) — catálogo de `events.type` e propagação de `trace_id`
- [docs/glossario.md](glossario.md) — mapeamento PT ↔ EN

