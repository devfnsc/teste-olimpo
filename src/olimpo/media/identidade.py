"""Vínculos locais entre assets e as âncoras de identidade da persona."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from olimpo.core.db import session_scope

COLUNA_POR_ANCORA = {
    "face": "face_asset_id",
    "character_sheet": "character_sheet_asset_id",
    "close_up_face": "close_up_face_asset_id",
    "close_up_detail": "close_up_detail_asset_id",
}


@dataclass(frozen=True, slots=True)
class ReferenciaDeEntrada:
    asset_id: UUID
    papel: str = "face"
    nota: str = ""


@dataclass(frozen=True, slots=True)
class ResultadoDeIdentidade:
    asset_id: UUID


async def definir_ancora(persona_id: UUID, ancora: str, asset_id: UUID) -> None:
    """Liga um asset existente a uma âncora e atualiza seu papel."""
    try:
        coluna = COLUNA_POR_ANCORA[ancora]
    except KeyError as exc:
        raise ValueError(f"âncora desconhecida: {ancora!r}") from exc
    async with session_scope() as sessao:
        existe = (await sessao.execute(
            text("SELECT 1 FROM media_assets WHERE id = :asset"), {"asset": asset_id}
        )).first()
        if not existe:
            raise ValueError(f"asset não encontrado: {asset_id}")
        persona = (await sessao.execute(
            text(f"UPDATE personas SET {coluna} = :asset WHERE id = :persona RETURNING id"),
            {"asset": asset_id, "persona": persona_id},
        )).scalar()
        if not persona:
            raise ValueError(f"persona não encontrada: {persona_id}")
        await sessao.execute(
            text("UPDATE media_assets SET role = CAST(:papel AS media_role), persona_id = :persona WHERE id = :asset"),
            {"papel": ancora, "persona": persona_id, "asset": asset_id},
        )


async def propor_rostos(*args: object, **kwargs: object) -> list[ResultadoDeIdentidade]:
    raise RuntimeError("geração de identidade exige um provider direto configurado")


async def gerar_figurino(*args: object, **kwargs: object) -> UUID:
    raise RuntimeError("geração de figurino exige um provider direto configurado")


async def gerar_ancora(*args: object, **kwargs: object) -> ResultadoDeIdentidade:
    raise RuntimeError("geração de âncora exige um provider direto configurado")


