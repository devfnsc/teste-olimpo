# AppRunCloud — inventário somente leitura

**Estado:** endpoints de leitura conferidos com o
[OpenAPI da AppRunCloud](https://www.appruncloud.com/v1/openapi.json).

Este contrato descreve a tela de inventário e o resumo do painel. A tela não
altera instâncias nem executa ações no Instagram. O backend do Olimpo faz estas
consultas à AppRunCloud:

| Método e caminho | Uso na tela |
|---|---|
| `GET /v1/instances?org_id={uuid}` | Lista instâncias e os dados básicos retornados pela central. |
| `GET /v1/instances/{id}/account?org_id={uuid}` | Consulta a conta conectada à instância. |
| `GET /v1/instances/{id}/instagram/accounts?org_id={uuid}` | Lista todas as contas Instagram logadas no app da instância. |
| `GET /v1/instances/{id}/device?org_id={uuid}` | Consulta o estado e as informações do dispositivo. |

Todas as chamadas usam `Authorization: Bearer ark_…`. Configure no ambiente
do backend `APPRUNCLOUD_API_KEY` e `APPRUNCLOUD_ORG_ID`; a chave deve pertencer
à organização indicada. `APPRUNCLOUD_BASE_URL` é opcional e, por padrão,
aponta para `https://www.appruncloud.com`. O timeout padrão é 30 segundos.

No OpenAPI, `GET /v1/instances/{id}/instagram/accounts` exige o `id` da rota e
`org_id` na query, ambos UUIDs. A resposta `400` está descrita como parâmetro
inválido ou ausente. O contrato não afirma que uma instância parada, por si só,
impeça essa leitura; por isso, esse estado não deve ser tratado como causa
confirmada de um `400`.

Ao carregar a listagem detalhada, o Olimpo consulta a conta ativa, todas as
contas Instagram logadas e o dispositivo para no máximo seis instâncias por
consulta. IDs inválidos e falhas parciais de detalhe não impedem a exibição das
demais instâncias. A listagem simples não faz essas consultas adicionais.

O router local correspondente é
`GET /v1/integrations/appruncloud/instances`, com os detalhes expostos por
`GET /v1/integrations/appruncloud/instances/{instance_id}/account` e
`GET /v1/integrations/appruncloud/instances/{instance_id}/instagram/accounts` e
`GET /v1/integrations/appruncloud/instances/{instance_id}/device`. A autenticação
da AppRunCloud permanece no backend e não é enviada ao navegador.

## Fora do escopo desta tela

A especificação também descreve operações que alteram contas e dispositivos.
Elas não fazem parte deste contrato de inventário e não são chamadas por essas
rotas GET.

