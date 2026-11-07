"""Tipos compartilhados pelos providers de geração de mídia."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class Route(StrEnum):
    GATEWAY = "gateway"
    DIRECT = "direct"


@dataclass(slots=True)
class GenerationRequest:
    kind: MediaKind
    prompt: str
    reference_images: list[str | bytes] = field(default_factory=list)
    model: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    seed: int | None = None
    count: int = 1
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_direct(self) -> bool:
        """Referências, vídeo e áudio não passam pelo gateway."""
        return bool(self.reference_images) or self.kind in {
            MediaKind.VIDEO,
            MediaKind.AUDIO,
        }


@dataclass(slots=True)
class GeneratedAsset:
    url: str | None = None
    conteudo: bytes | None = None
    mime: str | None = None
    provider_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MediaProvider(Protocol):
    route: Route

    def supports(self, request: GenerationRequest) -> bool: ...

    async def generate(self, request: GenerationRequest) -> list[GeneratedAsset]: ...


