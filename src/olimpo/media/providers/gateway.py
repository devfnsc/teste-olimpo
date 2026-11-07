"""Guarda que mantém geração de imagem fora do LiteLLM."""

from __future__ import annotations

from .base import GeneratedAsset, GenerationRequest, Route


class GatewayImageProvider:
    """Provider desativado: a sonda do gateway gera imagens cobradas."""

    route = Route.GATEWAY

    def supports(self, request: GenerationRequest) -> bool:
        return False

    async def generate(self, request: GenerationRequest) -> list[GeneratedAsset]:
        raise RuntimeError(
            "geração de imagem pelo gateway está desativada; use o provider direto"
        )


