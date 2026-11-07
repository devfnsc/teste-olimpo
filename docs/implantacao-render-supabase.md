# Demonstração no Render com Supabase

Este blueprint sobe somente a API e o painel. Não sobe worker ou beat; o
despacho permanece desativado e o interruptor geral fica ligado. O objetivo é
validar a interface e a consulta de inventário, não executar tarefas externas.

## Preparar o Supabase

1. Crie um projeto PostgreSQL para a demonstração.
2. Copie a conexão PostgreSQL com TLS para `DATABASE_URL` no Render. Para o
   plano gratuito do Supabase, prefira o pooler compartilhado em modo de sessão
   (porta `5432`) e copie a URL exibida em **Connect** no painel do Supabase.
   O endpoint direto do plano gratuito usa IPv6, enquanto o Render não oferece
   saída IPv6; portanto, a URL direta só serve se o projeto Supabase tiver
   conectividade IPv4 habilitada. O modo de sessão funciona com o pool SQLAlchemy
   da API e com o processo síncrono que aplica as migrações. Preserve
   `sslmode=require`.
3. Confirme que as extensões `uuid-ossp`, `vector`, `pg_trgm` e `pgcrypto` estão
   disponíveis. A primeira migração as habilita.
4. Não use a chave `service_role` do Supabase no navegador. O Olimpo se conecta
   ao PostgreSQL pelo backend.

## Criar os serviços no Render

1. Envie a pasta `olimpo-main` para um repositório Git privado.
2. No Render, crie um Blueprint usando o repositório e o arquivo `render.yaml`.
3. Informe os valores solicitados: `DATABASE_URL`, `PANEL_ACCESS_PASSWORD`,
   `APPRUNCLOUD_API_KEY` e `APPRUNCLOUD_ORG_ID`. Os segredos não ficam no Git.
4. O Render gera `API_TOKEN` e `PANEL_SESSION_SECRET`. A senha do painel deve
   ser forte e compartilhada apenas com quem fará a demonstração.
5. Aguarde o build e confira `/health` na API. A aplicação executa as
   migrações pendentes antes de iniciar a API.
6. Abra a URL do serviço `olimpo-panel` e entre com `PANEL_ACCESS_PASSWORD`.

O painel chama a API por um proxy no servidor Next.js. O `API_TOKEN` não é
incluído no JavaScript enviado ao navegador. A API bloqueia `/v1` em produção
se o token estiver ausente e rejeita chamadas sem credencial válida.

No Render, o proxy do painel aceita somente `GET` para saúde, visão geral,
contas, personas, servidores, inventário AppRunCloud e leituras visuais de
mídias, arquivos, marcas, identidade da persona, figurinos e opções/estado de
geração. Isso permite consultar a galeria e montar as telas sem expor a chave
da API ao navegador. O proxy recusa todos os métodos de escrita; uploads,
alterações, exclusões e pedidos de geração não ficam disponíveis nesta demo.

No desenvolvimento local do painel, estão disponíveis as operações
administrativas já presentes nas telas de contas, personas e mídias, incluindo
ações em lote para situação, papel, rótulos e vínculo de persona. O nível de
autonomia em lote não é permitido pelo proxy local. O proxy local também não
libera operações em servidores, automação, integrações externas ou geração de
conteúdo. A exclusão de conta exige a confirmação explícita que a tela já
solicita. Escritas locais exigem que `OLIMPO_API_URL` aponte para `localhost` ou
loopback.

No plano gratuito, o painel alcança a API pela URL HTTPS pública. O Blueprint
preenche `OLIMPO_API_URL` a partir da URL externa atribuída pelo Render ao
serviço `olimpo-api`, evitando depender de um subdomínio fixo. Serviços
gratuitos do Render não recebem tráfego pela rede privada. A chamada continua
passando pelo proxy e pelo `API_TOKEN` mantido no servidor.

## Limites desta demonstração

- A conexão AppRunCloud é usada apenas nas três rotas de leitura de instâncias,
  conta conectada e informações do dispositivo.
- A visão geral detalha conta e dispositivo para no máximo seis instâncias por
  atualização; a consulta de listagem continua trazendo o total da central.
- Não há worker/beat no blueprint. O código de geração e tarefas não roda na
  nuvem nesta configuração.
- Arquivos de mídia ficam em armazenamento temporário do serviço. Eles podem
  desaparecer em reinício ou novo deploy; não use esta configuração para
  manter referências de identidade. Antes disso, conecte armazenamento
  persistente, como Supabase Storage.
- Os planos gratuitos podem suspender serviços ociosos e têm limitações próprias.
  A URL pode demorar a responder quando o serviço voltar a iniciar.
- O blueprint descreve os recursos; ele não cria o projeto Supabase nem
  configura credenciais por conta própria.

## O que falta para publicar

O código e o blueprint estão preparados, mas ainda não há implantação online.
Para avançar, será necessário:

1. Informar o endereço do repositório GitHub que receberá este projeto e a
   branch que deve ser publicada. Se o repositório ainda não existir, ele
   precisa ser criado e conectado ao Render.
2. Criar ou escolher o projeto Supabase e cadastrar no Render a conexão
   PostgreSQL com TLS em `DATABASE_URL`. A senha e a URL devem ser fornecidas
   diretamente nos campos protegidos do Render, nunca em arquivos versionados
   ou mensagens do repositório.
3. Criar ou escolher a conta/ambiente Render que hospedará os dois serviços e
   configurar `PANEL_ACCESS_PASSWORD`. O blueprint gera os segredos da API e
   da sessão do painel.
4. Decidir se a demonstração online precisa consultar o AppRunCloud. Se sim,
   cadastrar `APPRUNCLOUD_API_KEY` e `APPRUNCLOUD_ORG_ID` nos segredos do
   serviço `olimpo-api`; sem eles, a tela continua disponível, mas mostra que a
   conexão não foi configurada.
5. Após a primeira publicação, compartilhar as URLs geradas pelo Render para
   conferir o login, o painel e a resposta `/health` da API.

No primeiro deploy bem-sucedido da API, o Render executa uma única vez o seed
fictício `python -m olimpo.db.seed`. Ele cria Luna Prado e a conta de exemplo
para que a visão geral não apareça vazia. Use um projeto Supabase dedicado à
demonstração: o seed acrescenta esses dados e não deve ser executado num banco
compartilhado com dados reais. O comando é idempotente e não roda a cada
reinicialização.

Não é necessário informar agora credenciais de provedores de texto ou imagem:
as opções de geração ainda são apenas catálogo visual e não fazem chamadas
externas. Também não é necessário configurar domínio próprio; o Render fornece
URLs para a demonstração.

