# ADR-0015: Limite de duas contas por persona

- **Status:** Aceito
- **Data:** 2026-11-05
- **Decisores:** equipe Olimpo
- **Refina:** [ADR-0013](0013-persona-separada-da-conta.md)
- **Migração:** [`0011_limite_duas_contas_por_persona.sql`](../../db/migrations/0011_limite_duas_contas_por_persona.sql)

## Contexto

O modelo separa persona de login e permite que uma conta pertença a no máximo
uma persona. A cardinalidade inversa estava aberta, embora o fluxo do produto
precise de um limite simples e previsível.

## Decisão

Uma persona pode ser associada a **zero, uma ou duas contas**. A terceira
associação é recusada. A regra vale para criação, edição, associação em lote e
escritas diretas no banco.

## Alternativas consideradas

| Alternativa | Motivo para não escolher |
|---|---|
| Uma conta por persona | Impede uma persona de estar representada em dois logins autorizados. |
| Quantidade ilimitada | Não corresponde à regra operacional definida para o produto. |
| Validar apenas no painel | Outros clientes da API e scripts poderiam ultrapassar o limite. |

## Consequências

- A API responde `409` quando um vínculo ultrapassaria o limite.
- O banco serializa mudanças simultâneas e aplica a mesma regra em qualquer
  caminho de escrita.
- A migração interrompe a aplicação se já existir persona com mais de duas
  contas; os vínculos precisam ser revisados antes de continuar.
- O painel mostra a contagem `0/2`, `1/2` ou `2/2` e desativa personas cheias
  nos seletores de associação.

## Revisitar quando

O domínio precisar de uma cardinalidade diferente, com um caso de uso e uma
regra de associação documentados.

