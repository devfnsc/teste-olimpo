"""Ordem das referências de identidade.

Este é o teste mais importante do subsistema de geração, e o que ele protege
não falha com erro: falha com uma pessoa levemente diferente.

Não existe semente, LoRA nem embedding por trás da consistência facial. Ela
depende de as imagens serem reenviadas NA ORDEM certa, porque as tags do
prompt (`@image1`, `@image2`…) apontam para posições do array. Se a lista
compactar e alguém indexar por posição fixa, a roupa passa a ser copiada da
referência de rosto — e a única evidência é o resultado parecer "quase" a
personagem.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from olimpo.media.providers.base import GenerationRequest, MediaKind, Route
from olimpo.media.providers.gateway import GatewayImageProvider
from olimpo.media.servico import ContextoDaPersona
from olimpo.prompts.tipos import ORDEM_REFERENCIAS, Persona


def ctx(*papeis: str) -> ContextoDaPersona:
    """Contexto com os papéis informados, na ordem informada."""
    from uuid import uuid4
    return ContextoDaPersona(
        persona=Persona(name="X"),
        referencias=[(p, uuid4()) for p in papeis],
        tem_rosto="face" in papeis,
    )


class TestOrdemDasReferencias:
    def test_a_ordem_canonica_comeca_pelo_rosto(self):
        """Se a primeira posição não for o rosto, não há identidade a
        preservar — as travas do prompt apontam para a imagem errada."""
        assert ORDEM_REFERENCIAS[0] == "face"
        assert ORDEM_REFERENCIAS[1] == "wardrobe"

    def test_papel_viaja_junto_do_asset(self):
        """A posição sozinha não diz o que a imagem é. Guardar o papel junto
        é o que permite resolver por papel em vez de por índice."""
        c = ctx("face", "wardrobe", "close_up_face")
        assert [p for p, _ in c.referencias] == ["face", "wardrobe", "close_up_face"]
        assert len(c.ids) == 3

    def test_ausencia_compacta_sem_perder_o_papel(self):
        """Uma persona sem folha de personagem tem o close de rosto na
        segunda posição do ARRAY — e é assim que o motor atribui as tags.
        O que não pode é alguém continuar achando que a posição 1 é a roupa."""
        c = ctx("face", "close_up_face", "close_up_detail")
        por_papel = dict(c.referencias)

        assert "wardrobe" not in por_papel
        # A segunda posição do array é o close de rosto…
        assert c.referencias[1][0] == "close_up_face"
        # …mas quem pergunta por "roupa" recebe nada, em vez de receber o
        # close de rosto por engano.
        assert por_papel.get("wardrobe") is None

    def test_extras_ficam_no_fim(self):
        """Fotos extras entram por último de propósito: colocá-las no meio
        deslocaria as posições das tags de todas as âncoras seguintes."""
        c = ctx("face", "wardrobe", "close_up_face", "close_up_detail",
                "product", "extra", "extra")
        papeis = [p for p, _ in c.referencias]
        assert papeis[-2:] == ["extra", "extra"]
        assert papeis.index("product") < papeis.index("extra")

    def test_sem_rosto_a_persona_nao_gera_com_identidade(self):
        assert ctx("wardrobe", "close_up_face").tem_rosto is False
        assert ctx("face").tem_rosto is True


class TestEscolhaDeProvider:
    """O gateway recusa imagem; o transporte direto ainda está desligado."""

    def test_catalogo_nao_marca_provider_sem_transporte_como_disponivel(self):
        """Chave configurada não substitui uma implementação de transporte."""
        from olimpo.media import modelos

        assert frozenset() == modelos.PROVIDERS_COM_TRANSPORTE
        assert all(
            modelos.motivo_de_indisponibilidade(modelo)
            for modelo in modelos.IMAGEM.values()
        )

    def test_api_recusa_enfileirar_sem_transporte(self):
        from fastapi import HTTPException

        from olimpo.api.routers.media import exigir_provider_imagem

        with pytest.raises(HTTPException) as erro:
            exigir_provider_imagem("fal-flux")

        assert erro.value.status_code == 503
        assert "transporte" in str(erro.value.detail)

    @pytest.mark.asyncio
    async def test_rotas_de_geracao_falham_antes_de_criar_jobs(self, monkeypatch):
        from fastapi import HTTPException

        from olimpo.api.routers import media

        async def nao_enfileirar(*args, **kwargs):
            raise AssertionError("rota enfileirou sem provider implementado")

        monkeypatch.setattr(media, "enfileirar_foto", nao_enfileirar)
        monkeypatch.setattr(media, "enfileirar_identidade", nao_enfileirar)

        pedidos = [
            media.gerar(uuid4(), media.PedidoDeGeracao()),
            media.gerar_ancora(uuid4(), "face"),
            media.gerar_figurino(
                uuid4(), media.PedidoDeFigurino(texto_livre="camisa azul")
            ),
        ]
        for pedido in pedidos:
            with pytest.raises(HTTPException) as erro:
                await pedido
            assert erro.value.status_code == 503

    def test_gateway_nao_atende_imagem_nenhuma(self):
        """Desligado em 2026-08-07, e o teste existe para que religar seja
        uma decisão e não um descuido.

        O alias `olimpo-image` saiu do LiteLLM porque a sonda de saúde
        (`background_health_checks`, a cada 60 s) **gera uma imagem real** em
        deployment com `mode: image_generation`. Queimou US$ 36 em cerca de
        nove horas, sem um único pedido do Olimpo — duas imagens por minuto,
        dia e noite.

        Quem for religar precisa antes garantir que a sonda não alcança o
        deployment. Trocar este teste sem isso repete a conta.
        """
        req = GenerationRequest(kind=MediaKind.IMAGE, prompt="uma foto")
        assert not GatewayImageProvider().supports(req)

    def test_texto_puro_tem_catalogo_mas_transporte_nao_ativo(self):
        """O registro de endpoint não significa que exista cliente funcional."""
        from olimpo.media import modelos

        assert modelos.resolver_imagem("fal-flux").t2i
        assert modelos.resolver_imagem("fal-seedream").t2i
        assert modelos.motivo_de_indisponibilidade(
            modelos.resolver_imagem("fal-flux")
        )

    def test_cloudflare_aparece_no_catalogo_mas_fica_desabilitado(self):
        """Transporte isolado não ativa o fluxo de geração de ponta a ponta."""
        from olimpo.media import modelos

        modelo = modelos.resolver_imagem("cloudflare-flux-2-klein-4b")
        assert modelo.provider == "cloudflare"
        assert modelo.max_referencias == 4
        assert modelos.motivo_de_indisponibilidade(modelo) == (
            "transporte Cloudflare implementado, mas ainda não integrado "
            "ao serviço de geração"
        )

    def test_gateway_recusa_com_referencia(self):
        req = GenerationRequest(
            kind=MediaKind.IMAGE, prompt="uma foto",
            reference_images=["https://x/rosto.jpg"],
        )
        assert not GatewayImageProvider().supports(req)
        assert req.needs_direct

    @pytest.mark.parametrize("tipo", [MediaKind.VIDEO, MediaKind.AUDIO])
    def test_gateway_recusa_video_e_voz(self, tipo):
        req = GenerationRequest(kind=tipo, prompt="x")
        assert not GatewayImageProvider().supports(req)
        assert req.needs_direct

    def test_rota_e_registrada(self):
        """Saber por onde a geração passou é o que permite atribuir custo e
        latência depois."""
        assert GatewayImageProvider().route is Route.GATEWAY


class TestTraducaoDeTags:
    """`@image1` não significa nada para o fal. A tradução para ordinal
    posicional é o que preserva o roteamento entre as referências."""

    def test_traduz_para_ordinal(self):
        from olimpo.media.modelos import limpar_prompt
        saida = limpar_prompt("Foto de @image1 vestindo a roupa de @image2")
        assert "the first reference image" in saida
        assert "the second reference image" in saida
        assert "@image" not in saida

    def test_aceita_as_duas_grafias(self):
        """O photo studio usa `@image1`; o motor de vídeo usa `@image_1`."""
        from olimpo.media.modelos import limpar_prompt
        assert "the first reference image" in limpar_prompt("@image_1 aparece")
        assert "the first reference image" in limpar_prompt("@image1 aparece")

    def test_tag_sem_numero_nao_engole_a_numerada(self):
        """A ordem das substituições importa: tratar `@image_` antes de
        `@image_2` deixaria um '2' solto no texto."""
        from olimpo.media.modelos import limpar_prompt
        saida = limpar_prompt("@image_2 e @image_")
        assert "the second reference image" in saida
        assert "2" not in saida.replace("the second reference image", "")

