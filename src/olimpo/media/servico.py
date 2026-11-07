"""Contratos e regras locais do serviço de geração de fotos."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from olimpo.prompts.tipos import Persona


@dataclass(slots=True)
class ContextoDaPersona:
    persona: Persona
    referencias: list[tuple[str, UUID]] = field(default_factory=list)
    tem_rosto: bool = False

    @property
    def ids(self) -> list[UUID]:
        return [asset_id for _, asset_id in self.referencias]


@dataclass(slots=True)
class PedidoDeFoto:
    persona_id: UUID
    local: str = "coffee-shop"
    hora: str = "afternoon"
    pose: str = "front"
    stance: str = "standing"
    expressao: str = "natural"
    olhar: str = "at-camera"
    aspect_ratio: str = "9:16"
    quantidade: int = 1
    wardrobe_item_id: UUID | None = None
    wardrobe_text: str = ""
    hairstyle_text: str = ""
    brand_id: UUID | None = None
    prop_text: str = ""
    modelo: str | None = None
    resolucao: str | None = None
    seed: int | None = None


_PRIORIDADE = {
    "face": 100,
    "wardrobe": 90,
    "product": 80,
    "close_up_face": 70,
    "close_up_detail": 60,
    "extra": 10,
}


def limitar_referencias[T](
    referencias: list[tuple[str, T]],
    limite: int,
) -> tuple[list[tuple[str, T]], list[str]]:
    """Corta pelo valor semântico e preserva a ordem dos sobreviventes."""
    if not referencias:
        return [], []
    if limite < 0:
        raise ValueError("o limite de referências não pode ser negativo")
    if len(referencias) <= limite:
        return list(referencias), []

    escolhidos = sorted(
        range(len(referencias)),
        key=lambda indice: (-_PRIORIDADE.get(referencias[indice][0], 0), indice),
    )[:limite]
    indices = set(escolhidos)
    mantidas = [referencia for i, referencia in enumerate(referencias) if i in indices]
    descartados = [papel for i, (papel, _) in enumerate(referencias) if i not in indices]
    return mantidas, descartados


async def gerar_foto(
    pedido: PedidoDeFoto,
    *,
    job_id: UUID | None = None,
) -> list[UUID]:
    """Valida o pedido antes da etapa de provider, ainda não contratada aqui.

    O repositório documenta os endpoints e o registro, mas não um contrato de
    transporte para fal/OpenAI. Falhar explicitamente impede que uma chamada
    incompleta seja tratada como geração bem-sucedida ou tente rede por engano.
    """
    if pedido.quantidade < 1 or pedido.quantidade > 8:
        raise ValueError("quantidade deve estar entre 1 e 8")
    if not pedido.aspect_ratio.strip():
        raise ValueError("aspect_ratio não pode ser vazio")
    raise RuntimeError(
        "execução do provider de imagem não possui contrato de transporte "
        "implementado neste pacote"
    )


