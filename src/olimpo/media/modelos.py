"""Registro local dos modelos de mídia e de seus contratos confirmados."""

from __future__ import annotations

import re
from dataclasses import dataclass

from olimpo.core.config import settings
from olimpo.media.providers.cloudflare import MODEL_ID as CLOUDFLARE_MODEL_ID


@dataclass(frozen=True, slots=True)
class ModeloImagem:
    id: str
    label: str
    provider: str
    edit: str
    t2i: str | None
    resolucoes: tuple[str, ...] = ()
    aspectos_aceitos: tuple[str, ...] = ("9:16", "4:5", "1:1", "16:9", "3:4")
    max_referencias: int = 10
    suporta_fidelidade: bool = False


@dataclass(frozen=True, slots=True)
class ModeloVideo:
    id: str
    label: str
    provider: str
    endpoint: str
    duracoes: tuple[int, ...] = ()
    resolucoes: tuple[str, ...] = ()
    gera_audio: bool = False
    bloqueia_rosto_real: bool = False


# Endpoints transcritos da tabela do registro em docs/13; as assimetrias de
# prefixo são parte do contrato do fal, não uma padronização nossa.
IMAGEM: dict[str, ModeloImagem] = {
    "fal-flux": ModeloImagem(
        "fal-flux", "FLUX.2", "fal", "fal-ai/flux-2/edit", "fal-ai/flux-2",
        max_referencias=4,
    ),
    "fal-nano-pro": ModeloImagem(
        "fal-nano-pro", "Nano Banana Pro", "fal",
        "fal-ai/nano-banana-pro/edit", "fal-ai/nano-banana",
        resolucoes=("1K", "2K", "4K"),
    ),
    "fal-nano": ModeloImagem(
        "fal-nano", "Nano Banana", "fal",
        "fal-ai/nano-banana/edit", "fal-ai/nano-banana",
    ),
    "openai-gpt-image-2": ModeloImagem(
        "openai-gpt-image-2", "GPT Image 2 (OpenAI)", "openai",
        "gpt-image-2", "gpt-image-2", resolucoes=("low", "medium", "high"),
    ),
    "fal-gpt-image-2": ModeloImagem(
        "fal-gpt-image-2", "GPT Image 2 (fal)", "fal",
        "openai/gpt-image-2/edit", "fal-ai/gpt-image-2",
        resolucoes=("low", "medium", "high"),
    ),
    "fal-seedream": ModeloImagem(
        "fal-seedream", "Seedream v5 Pro", "fal",
        "bytedance/seedream/v5/pro/edit",
        "bytedance/seedream/v5/pro/text-to-image",
        resolucoes=("1K", "2K"),
    ),
    "fal-seedream-lite": ModeloImagem(
        "fal-seedream-lite", "Seedream v5 Lite", "fal",
        "fal-ai/bytedance/seedream/v5/lite/edit",
        "fal-ai/bytedance/seedream/v5/lite/text-to-image",
        resolucoes=("2K", "3K", "4K"),
    ),
    "cloudflare-flux-2-klein-4b": ModeloImagem(
        "cloudflare-flux-2-klein-4b", "FLUX.2 Klein 4B", "cloudflare",
        CLOUDFLARE_MODEL_ID, CLOUDFLARE_MODEL_ID, max_referencias=4,
    ),
}

# Os endpoints de vídeo não aparecem no contrato local com seus caminhos
# completos. O registro fica vazio até haver um endpoint verificável, em vez
# de aceitar uma rota presumida que só falharia depois de enfileirar um job.
VIDEO: dict[str, ModeloVideo] = {}

# O catálogo descreve modelos conhecidos; não afirma que existe um cliente de
# transporte funcional. Este conjunto só muda quando um provider implementado
# e exercitado é conectado ao serviço de geração.
PROVIDERS_COM_TRANSPORTE: frozenset[str] = frozenset()

SEM_PREFIXO_FAL = frozenset({
    "openai/gpt-image-2/edit",
    "bytedance/seedream/v5/pro/edit",
    "bytedance/seedream/v5/pro/text-to-image",
})


def resolver_imagem(identificador: str | None = None) -> ModeloImagem:
    escolhido = identificador or "fal-flux"
    try:
        return IMAGEM[escolhido]
    except KeyError as exc:
        raise ValueError(
            f"modelo de imagem desconhecido: {escolhido!r}; "
            f"use um de {sorted(IMAGEM)}"
        ) from exc


def motivo_de_indisponibilidade(modelo: ModeloImagem) -> str | None:
    """Explica por que o modelo não pode ser chamado nesta instalação."""
    if modelo.provider not in PROVIDERS_COM_TRANSPORTE:
        if modelo.provider == "cloudflare":
            return (
                "transporte Cloudflare implementado, mas ainda não integrado "
                "ao serviço de geração"
            )
        return f"transporte do provider {modelo.provider!r} ainda não implementado"
    if modelo.provider == "fal" and not settings.fal_api_key:
        return "FAL_API_KEY não configurada"
    if modelo.provider == "openai" and not settings.openai_image_key:
        return "OPENAI_IMAGE_KEY não configurada"
    return None


FAL_ORDINALS = (
    "first", "second", "third", "fourth", "fifth",
    "sixth", "seventh", "eighth", "ninth", "tenth",
)
_TAG_NUMERADA = re.compile(r"@image_?(\d+)", re.IGNORECASE)
_TAG_GENERICA = re.compile(r"@image_?", re.IGNORECASE)


def limpar_prompt(texto: str) -> str:
    """Traduz tags posicionais para o vocabulário aceito pelos providers."""
    def traduzir(casamento: re.Match[str]) -> str:
        numero = int(casamento.group(1))
        if 1 <= numero <= len(FAL_ORDINALS):
            return f"the {FAL_ORDINALS[numero - 1]} reference image"
        return f"reference image number {numero}"

    traduzido = _TAG_NUMERADA.sub(traduzir, texto)
    traduzido = _TAG_GENERICA.sub("the reference image", traduzido)
    return " ".join(traduzido.split())


