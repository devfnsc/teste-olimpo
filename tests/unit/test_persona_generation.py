"""Testes locais da geração de personas sem chamadas externas."""

from __future__ import annotations

from typing import ClassVar

import httpx
import pytest

from olimpo.personas import generation


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("upstream", request=request, response=response)

    def json(self) -> dict:
        return self._payload


class FakeClient:
    responses: ClassVar[list[FakeResponse | Exception]] = []
    calls: ClassVar[int] = 0
    request_bodies: ClassVar[list[dict]] = []

    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, *_: object, **__: object) -> FakeResponse:
        type(self).calls += 1
        body = __.get("json")
        if isinstance(body, dict):
            type(self).request_bodies.append(body)
        response = type(self).responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.responses = []
    FakeClient.calls = 0
    FakeClient.request_bodies = []
    monkeypatch.setattr(generation.settings, "gemini_api_key", "local-test-key")
    monkeypatch.setattr(generation.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(generation.asyncio, "sleep", _no_sleep)
    return FakeClient


async def _no_sleep(_: float) -> None:
    return None


def valid_output() -> generation.GeneratedPersonaOutput:
    card: dict = {"schema_version": "1.0", "version": 1, "archetype": "influencer"}
    for block, fields in generation._REQUIRED_FIELDS.items():
        card[block] = {field: "conteúdo coerente" for field in fields}
    card["identity"].update({
        "name": "Lia Teste", "apparent_age": 28,
        "location": {"city": "Recife", "state": "PE", "country": "Brasil"},
        "ai_disclosure": "Persona virtual fictícia.",
    })
    card["voice"]["examples"] = [f"Exemplo original {index}" for index in range(5)]
    card["lore"]["milestones"] = [
        {"age": "18", "event": f"Marco {index}", "impact": "amadurecimento"}
        for index in range(3)
    ]
    card["lore"]["phone_schedule"] = [
        {"days": "dias úteis", "start": f"{hour:02}:00", "end": f"{hour:02}:30",
         "context": "pausa", "phone_activities": "responder mensagens"}
        for hour in (12, 19, 21)
    ]
    card["niche"]["content_pillars"] = [
        {"name": "rotina", "description": "cotidiano", "share": 0.6},
        {"name": "bem-estar", "description": "hábitos", "share": 0.4},
    ]
    card["visual"]["canonical_description"] = "Descrição visual original e consistente."
    story = "Persona adulta fictícia com história, rotina e interesses coerentes. " * 4
    return generation.GeneratedPersonaOutput(narrative=story, persona_card=card)


def test_schema_tem_blocos_completos_e_limite_de_historia() -> None:
    schema = generation.response_schema()
    assert schema["required"] == ["narrative", "persona_card"]
    card = schema["properties"]["persona_card"]
    assert all(block in card["properties"] for block in generation._CARD_BLOCKS)
    assert "phone_schedule" in card["properties"]["lore"]["properties"]


def test_recusa_idade_inferior_a_18() -> None:
    with pytest.raises(ValueError):
        generation.PersonaGenerationInput(age=17)


def test_validacao_preserva_historia_e_rejeita_dados_fixos_incoerentes() -> None:
    output = valid_output()
    card = generation.validate_generated_persona(
        output, generation.PersonaGenerationInput(name="Lia Teste", city="Recife", age=28)
    )
    assert card["lore"]["canonical_narrative"] == output.narrative

    with pytest.raises(generation.PersonaGenerationError, match="idade informada"):
        generation.validate_generated_persona(
            valid_output(), generation.PersonaGenerationInput(age=30)
        )


@pytest.mark.asyncio
async def test_chave_gemini_ausente_explica_configuracao_com_503(
    fake_gemini: type[FakeClient], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generation.settings, "gemini_api_key", "")

    with pytest.raises(generation.PersonaGenerationError) as error:
        await generation.generate_persona(generation.PersonaGenerationInput())

    assert error.value.status_code == 503
    assert "Configure GEMINI_API_KEY" in str(error.value)
    assert fake_gemini.calls == 0


@pytest.mark.asyncio
async def test_repeticao_de_503_tem_sucesso_na_tentativa_seguinte(
    fake_gemini: type[FakeClient],
) -> None:
    output = valid_output()
    valid_json = output.model_dump_json()
    fake_gemini.responses = [
        FakeResponse(503),
        FakeResponse(503),
        FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": valid_json}]}}]}),
    ]

    generated, usage = await generation.generate_persona(generation.PersonaGenerationInput())

    assert fake_gemini.calls == 3
    assert generated.narrative == output.narrative
    assert usage["total_tokens"] == 0
    config = fake_gemini.request_bodies[-1]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "LOW", "includeThoughts": False}


@pytest.mark.asyncio
async def test_503_persistente_retorna_erro_transitorio_sem_expor_detalhes(
    fake_gemini: type[FakeClient],
) -> None:
    fake_gemini.responses = [FakeResponse(503) for _ in range(4)]

    with pytest.raises(generation.PersonaGenerationError) as error:
        await generation.generate_persona(generation.PersonaGenerationInput())

    assert error.value.status_code == 503
    assert "temporariamente indisponível" in str(error.value)
    assert fake_gemini.calls == 4


@pytest.mark.asyncio
async def test_falha_de_conexao_nao_gera_typeerror_no_tratamento(
    fake_gemini: type[FakeClient],
) -> None:
    request = httpx.Request("POST", "https://example.test")
    fake_gemini.responses = [httpx.ConnectError("connection refused", request=request)]

    with pytest.raises(generation.PersonaGenerationError) as error:
        await generation.generate_persona(generation.PersonaGenerationInput())

    assert error.value.status_code == 503
    assert "conectar ao Gemini" in str(error.value)


@pytest.mark.asyncio
async def test_timeout_tem_uma_retentativa_e_pode_retornar_resposta_valida(
    fake_gemini: type[FakeClient],
) -> None:
    output = valid_output()
    request = httpx.Request("POST", "https://example.test")
    fake_gemini.responses = [
        httpx.ReadTimeout("model is still generating", request=request),
        FakeResponse(200, {"candidates": [{"content": {"parts": [{
            "text": output.model_dump_json(),
        }]}}]}),
    ]

    generated, _ = await generation.generate_persona(generation.PersonaGenerationInput())

    assert fake_gemini.calls == 2
    assert generated.narrative == output.narrative


@pytest.mark.asyncio
async def test_resposta_interrompida_por_limite_de_tokens_fica_explicita(
    fake_gemini: type[FakeClient],
) -> None:
    fake_gemini.responses = [FakeResponse(200, {
        "candidates": [{"finishReason": "MAX_TOKENS"}],
        "usageMetadata": {"candidatesTokenCount": 8192},
    })]

    with pytest.raises(generation.PersonaGenerationError, match="8192"):
        await generation.generate_persona(generation.PersonaGenerationInput())

