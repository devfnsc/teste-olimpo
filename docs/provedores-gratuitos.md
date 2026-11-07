# Provedores gratuitos para protótipos

Pesquisa feita em 5 de novembro de 2026, usando páginas oficiais dos
provedores. Franquias e modelos podem mudar; confirme a cota no painel de cada
conta antes de testar. “Gratuito” aqui significa uma franquia limitada, não uso
ilimitado.

## Texto para histórias fictícias

**Gemini API — Gemini 2.5 Flash-Lite.** A página oficial de preços lista
entrada e saída sem cobrança na faixa gratuita para este modelo. A faixa
gratuita tem limites por modelo e projeto, exibidos no AI Studio, e informa que
o conteúdo pode ser usado para melhorar os produtos do Google. Use somente
personagens e dados de demonstração fictícios; não envie credenciais, dados de
contas reais ou informações privadas.

Fontes: [preços da Gemini API](https://ai.google.dev/gemini-api/docs/pricing) e
[limites por modelo](https://ai.google.dev/gemini-api/docs/rate-limits).

## Imagens para protótipos

**Cloudflare Workers AI — FLUX.1 [schnell].** A franquia do plano gratuito é
de 10.000 neurônios por dia, compartilhada entre os modelos Workers AI, com
reinício às 00:00 UTC. FLUX.1 [schnell] é text-to-image e retorna a imagem em
base64; a página do modelo declara retenção zero. Cada geração consome a
franquia segundo o preço do modelo, portanto a quantidade diária depende do
tamanho e dos parâmetros escolhidos.

**Cloudflare Workers AI — FLUX.2 [klein] 4B.** É uma opção de geração e edição
com imagens de referência, compatível com imagens-base de identidade. A API
usa `multipart/form-data` e aceita até quatro imagens de entrada. A página de
preços lista cobrança em neurônios; confirme a disponibilidade na franquia da
conta Cloudflare antes de adotá-lo como caminho gratuito.

Fontes: [franquia e preços](https://developers.cloudflare.com/workers-ai/platform/pricing/),
[FLUX.1 schnell](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)
e [FLUX.2 klein 4B](https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/).

## Alternativa com créditos pequenos

**Hugging Face Inference Providers.** Contas gratuitas recebem US$ 0,10 em
créditos mensais para experimentar. Os créditos são compartilhados entre os
provedores elegíveis; depois de consumidos, o uso pode gerar cobrança se houver
créditos pagos configurados. É adequado para comparar modelos, mas não para
gerar em volume.

Fonte: [preços e créditos do Hugging Face](https://huggingface.co/docs/inference-providers/en/pricing).

## Próximo passo técnico

O catálogo visual do painel ainda não chama esses serviços. Para uma prova
local, implementar primeiro um adaptador de texto e um adaptador de imagem,
ambos com chaves mantidas somente no backend, limite explícito de requisições,
tratamento de quota esgotada e gravação de cada resultado no acervo associado à
persona escolhida. Não enviar conteúdo gerado para contas ou plataformas a
partir deste fluxo de teste.

No Render gratuito, arquivos locais são temporários. Uma prova visual pode
mostrar as imagens durante a sessão, mas a retenção de resultados exige um
armazenamento persistente, como Supabase Storage. Veja também
[a preparação Render + Supabase](implantacao-render-supabase.md).

