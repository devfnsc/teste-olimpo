"""Armazenamento local, deduplicado pelo hash do conteúdo."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text

from olimpo.core.config import settings
from olimpo.core.db import session_scope

RAIZ = Path(settings.media_root)
EXTENSAO_POR_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}


def _dimensoes_jpeg(conteudo: bytes) -> tuple[int, int] | None:
    if not conteudo.startswith(b"\xff\xd8"):
        return None
    posicao = 2
    sof = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while posicao < len(conteudo):
        if conteudo[posicao] != 0xFF:
            posicao += 1
            continue
        while posicao < len(conteudo) and conteudo[posicao] == 0xFF:
            posicao += 1
        if posicao >= len(conteudo):
            return None
        marcador = conteudo[posicao]
        posicao += 1
        if marcador in {0x01, *range(0xD0, 0xDA)}:
            continue
        if posicao + 2 > len(conteudo):
            return None
        tamanho = struct.unpack(">H", conteudo[posicao : posicao + 2])[0]
        if tamanho < 2 or posicao + tamanho > len(conteudo):
            return None
        if marcador in sof:
            if tamanho < 7:
                return None
            altura, largura = struct.unpack(">HH", conteudo[posicao + 3 : posicao + 7])
            return (largura, altura) if largura and altura else None
        posicao += tamanho
    return None


def _u24_le(valor: bytes) -> int:
    return int.from_bytes(valor, "little")


def _dimensoes_webp(conteudo: bytes) -> tuple[int, int] | None:
    if len(conteudo) < 21 or conteudo[:4] != b"RIFF" or conteudo[8:12] != b"WEBP":
        return None
    tipo = conteudo[12:16]
    if tipo == b"VP8L" and len(conteudo) >= 25 and conteudo[20] == 0x2F:
        bits = struct.unpack("<I", conteudo[21:25])[0]
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if tipo == b"VP8X" and len(conteudo) >= 30:
        return _u24_le(conteudo[24:27]) + 1, _u24_le(conteudo[27:30]) + 1
    if tipo == b"VP8 " and len(conteudo) >= 30 and conteudo[23:26] == b"\x9d\x01\x2a":
        largura, altura = struct.unpack("<HH", conteudo[26:30])
        return largura & 0x3FFF, altura & 0x3FFF
    return None


def dimensoes(conteudo: bytes) -> tuple[int, int] | None:
    """Lê dimensões do cabeçalho; entrada truncada/desconhecida retorna ``None``."""
    try:
        if len(conteudo) >= 24 and conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
            if conteudo[12:16] != b"IHDR":
                return None
            largura, altura = struct.unpack(">II", conteudo[16:24])
            return (largura, altura) if largura and altura else None
        if len(conteudo) >= 10 and conteudo.startswith((b"GIF87a", b"GIF89a")):
            largura, altura = struct.unpack("<HH", conteudo[6:10])
            return (largura, altura) if largura and altura else None
        return _dimensoes_jpeg(conteudo) or _dimensoes_webp(conteudo)
    except (IndexError, struct.error):
        return None


async def guardar(
    conteudo: bytes,
    *,
    persona_id: UUID | None = None,
    role: str = "generated",
    kind: str = "image",
    mime: str,
    label: str | None = None,
    source: str | None = None,
    source_url: str | None = None,
    prompt: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    aspect_ratio: str | None = None,
    params: dict[str, Any] | None = None,
    reference_ids: list[UUID] | None = None,
) -> UUID:
    """Grava bytes localmente e cria/reaproveita o asset pelo SHA-256."""
    if not conteudo:
        raise ValueError("não é possível guardar mídia vazia")
    digest = hashlib.sha256(conteudo).hexdigest()
    extensao = EXTENSAO_POR_MIME.get(mime)
    if extensao is None:
        raise ValueError(f"mime sem extensão de armazenamento: {mime!r}")
    relativo = Path("assets") / digest[:2] / f"{digest}{extensao}"
    destino = RAIZ / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists():
        temporario = destino.with_suffix(destino.suffix + ".tmp")
        temporario.write_bytes(conteudo)
        temporario.replace(destino)

    tamanho = dimensoes(conteudo) if kind == "image" else None
    async with session_scope() as sessao:
        existente = (await sessao.execute(
            text("SELECT id FROM media_assets WHERE content_hash = :hash"),
            {"hash": digest},
        )).scalar()
        if existente:
            return cast(UUID, existente)
        criado = (await sessao.execute(text("""
            INSERT INTO media_assets (
                persona_id, kind, role, storage_path, source_url, content_hash,
                mime, width, height, bytes, prompt, provider, model,
                aspect_ratio, params, reference_ids, label, source
            ) VALUES (
                :persona_id, CAST(:kind AS media_kind), CAST(:role AS media_role),
                :storage_path, :source_url, :content_hash, :mime, :width, :height,
                :bytes, :prompt, :provider, :model, :aspect_ratio,
                CAST(:params AS jsonb), :reference_ids, :label, :source
            ) RETURNING id
        """), {
            "persona_id": persona_id,
            "kind": kind,
            "role": role,
            "storage_path": relativo.as_posix(),
            "source_url": source_url,
            "content_hash": digest,
            "mime": mime,
            "width": tamanho[0] if tamanho else None,
            "height": tamanho[1] if tamanho else None,
            "bytes": len(conteudo),
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "params": params or {},
            "reference_ids": reference_ids or [],
            "label": label,
            "source": source,
        })).scalar_one()
        return cast(UUID, criado)


