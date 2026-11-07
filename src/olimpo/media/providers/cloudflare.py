"""Transporte direto para FLUX.2 Klein 4B no Cloudflare Workers AI.

O provider implementa apenas geração/edição de imagens. A ativação no catálogo
depende de o serviço de identidade e mídia estar ligado a este transporte.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any, cast

import httpx

from .base import GeneratedAsset, GenerationRequest, MediaKind, Route

MODEL_ID = "@cf/black-forest-labs/flux-2-klein-4b"
_MIME_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),
)


class CloudflareWorkersAIProvider:
    """Cliente HTTP enxuto; não coloca credenciais em URL, log ou exceção."""

    route = Route.DIRECT

    def __init__(
        self,
        account_id: str,
        api_token: str,
        *,
        timeout: float = 120,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.account_id = account_id.strip()
        self.api_token = api_token.strip()
        self.timeout = timeout
        self.transport = transport
        if self.account_id and not re.fullmatch(r"[0-9a-fA-F]{32}", self.account_id):
            raise ValueError("CLOUDFLARE_ACCOUNT_ID deve ter 32 caracteres hexadecimais")

    def supports(self, request: GenerationRequest) -> bool:
        return (
            request.kind is MediaKind.IMAGE
            and request.model in {None, MODEL_ID}
            and all(isinstance(image, bytes) for image in request.reference_images)
        )

    async def generate(self, request: GenerationRequest) -> list[GeneratedAsset]:
        if not self.account_id or not self.api_token:
            raise RuntimeError("credenciais do Cloudflare Workers AI não configuradas")
        if request.kind is not MediaKind.IMAGE or request.model not in {None, MODEL_ID}:
            raise ValueError("o provider Cloudflare configurado aceita somente imagem FLUX.2 Klein 4B")
        if not all(isinstance(image, bytes) for image in request.reference_images):
            raise ValueError("o transporte Cloudflare exige referências como bytes")
        if not request.prompt.strip():
            raise ValueError("o prompt não pode estar vazio")
        if len(request.reference_images) > 4:
            raise ValueError("FLUX.2 Klein 4B aceita no máximo quatro imagens de referência")
        if request.count < 1 or request.count > 4:
            raise ValueError("a quantidade deve estar entre 1 e 4")

        width, height = _dimensions(request.aspect_ratio)
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{MODEL_ID}"
        )
        headers = {"Authorization": f"Bearer {self.api_token}"}
        assets: list[GeneratedAsset] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            for index in range(request.count):
                fields: list[tuple[str, tuple[Any, ...]]] = [
                    ("prompt", (None, request.prompt)),
                    ("width", (None, str(width))),
                    ("height", (None, str(height))),
                ]
                seed = request.seed + index if request.seed is not None else None
                if seed is not None:
                    fields.append(("seed", (None, str(seed))))
                for ref_index, content in enumerate(request.reference_images):
                    image_bytes = cast(bytes, content)
                    mime = _mime(image_bytes)
                    fields.append((
                        f"input_image_{ref_index}",
                        (f"reference-{ref_index}.{_extension(mime)}", image_bytes, mime),
                    ))

                try:
                    response = await client.post(url, headers=headers, files=fields)
                except httpx.HTTPError as exc:
                    raise RuntimeError("falha de conexão com Cloudflare Workers AI") from exc

                if response.status_code >= 400:
                    raise RuntimeError(
                        f"Cloudflare Workers AI respondeu HTTP {response.status_code}"
                    )
                try:
                    payload = response.json()
                    result = payload["result"]
                    if not isinstance(result, dict):
                        raise TypeError("result não é um objeto")
                    encoded = result["image"]
                    image = base64.b64decode(encoded, validate=True)
                    mime = _mime(image)
                except (ValueError, KeyError, TypeError, binascii.Error) as exc:
                    raise RuntimeError("resposta de imagem inválida do Cloudflare Workers AI") from exc

                assets.append(GeneratedAsset(
                    conteudo=image,
                    mime=mime,
                    provider_ref=result.get("id"),
                    metadata={"model": MODEL_ID, "seed": seed, "width": width, "height": height},
                ))

        return assets


def _dimensions(aspect_ratio: str | None) -> tuple[int, int]:
    try:
        width_ratio, height_ratio = (int(part) for part in (aspect_ratio or "1:1").split(":"))
    except (ValueError, TypeError) as exc:
        raise ValueError("aspect_ratio inválido; use o formato largura:altura") from exc
    ratio = width_ratio / height_ratio
    if width_ratio < 1 or height_ratio < 1 or ratio < 0.25 or ratio > 4:
        raise ValueError("aspect_ratio deve estar entre 1:4 e 4:1")
    scale = 1024 / max(width_ratio, height_ratio)
    width = max(256, min(1920, round(width_ratio * scale / 16) * 16))
    height = max(256, min(1920, round(height_ratio * scale / 16) * 16))
    return width, height


def _mime(content: bytes) -> str:
    for signature, mime in _MIME_SIGNATURES:
        if content.startswith(signature):
            if mime == "image/webp" and content[8:12] != b"WEBP":
                continue
            return mime
    raise ValueError("formato de imagem não reconhecido")


def _extension(mime: str) -> str:
    return {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]

