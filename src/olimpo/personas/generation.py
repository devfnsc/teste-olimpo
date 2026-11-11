"""Geração de persona via Gemini Flash, com validação antes da gravação."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from olimpo.core.config import settings

log = structlog.get_logger(__name__)


class PersonaGenerationInput(BaseModel):
    """Restrições opcionais fornecidas pela pessoa operadora."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    age: int | None = Field(default=None, ge=18, le=100)


class GeneratedPersonaOutput(BaseModel):
    """Uma resposta contém a história-base e o card estruturado completo."""

    model_config = ConfigDict(extra="forbid")

    narrative: str = Field(min_length=100)
    persona_card: dict[str, Any]

    @field_validator("narrative")
    @classmethod
    def narrative_max_100_lines(cls, value: str) -> str:
        if len(value.splitlines()) > 100:
            raise ValueError("a história deve ter no máximo 100 linhas")
        if "[preencher]" in value.casefold() or "lorem ipsum" in value.casefold() or re.search(
            r"\bTODO\b", value, flags=re.IGNORECASE
        ):
            raise ValueError("a história contém texto provisório")
        return value.strip()


class PersonaGenerationError(Exception):
    """Erro amigável sem expor chave ou resposta bruta do Gemini."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


_CARD_BLOCKS = (
    "identity", "voice", "visual", "personality", "lore", "niche",
    "taboos", "cadence", "commercial",
)

_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "identity": (
        "name", "display_name", "handle", "apparent_age", "gender", "location",
        "occupation", "language", "bio", "ai_disclosure",
    ),
    "voice": (
        "tone", "register", "slang", "caption_length", "emoji", "hashtag",
        "examples", "never_say",
    ),
    "visual": (
        "canonical_description", "aesthetic", "palette", "recurring_settings",
        "wardrobe", "forbidden_visuals",
    ),
    "personality": (
        "traits", "values", "irritations", "moves_her", "default_mood", "humor",
        "mood_range", "insecurities", "opinions",
    ),
    "lore": (
        "backstory", "milestones", "routine", "phone_schedule", "current_situation",
        "relationships", "pets",
    ),
    "niche": (
        "primary", "secondary", "audience", "content_pillars", "formats",
        "pain_points", "references",
    ),
    "taboos": (
        "topics", "banned_words", "never_interactions", "sensitive_handling", "hard_blocks",
    ),
    "cadence": ("posts_per_day", "stories_per_day", "preferred_hours", "most_active_days"),
    "commercial": ("accepts_sponsored", "blocked_categories", "disclosure"),
}


def _schema_object(properties: dict[str, dict[str, Any]], required: list[str]) -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": properties,
        "required": required,
    }


def _schema_string(description: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "STRING"}
    if description:
        schema["description"] = description
    return schema


def _object(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"type": "OBJECT", "properties": fields, "required": list(fields)}


def _array(item: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "ARRAY", "items": item or {"type": "STRING"}}


def response_schema() -> dict[str, Any]:
    """Gemini JSON schema with concrete object items for routine and pillars."""
    location = _object({k: {"type": "STRING"} for k in ("city", "state", "country")})
    list_fields = {
        "tone", "slang", "never_say", "examples", "traits", "values", "irritations",
        "moves_her", "topics", "banned_words", "never_interactions", "hard_blocks",
        "secondary", "formats", "preferred_hours", "most_active_days", "blocked_categories",
        "forbidden_visuals", "recurring_settings", "references", "mood_range",
        "insecurities", "opinions", "relationships", "pets", "pain_points",
    }
    phone_window = _object({k: {"type": "STRING"} for k in (
        "days", "start", "end", "context", "phone_activities"
    )})
    milestone = _object({k: {"type": "STRING"} for k in ("age", "event", "impact")})
    pillar = _object({k: {"type": "STRING"} for k in ("name", "description")}
                     | {"share": {"type": "NUMBER", "minimum": 0, "maximum": 1}})
    field_schema: dict[str, dict[str, Any]] = {
        "identity.location": location,
        "voice.slang": _object({"uses": _array(), "never": _array()}),
        "voice.emoji": _object({"style": {"type": "STRING"}, "frequency": {"type": "STRING"}}),
        "voice.hashtag": _object({"style": {"type": "STRING"}, "frequency": {"type": "STRING"}}),
        "visual.palette": _object({"primary": _array(), "accent": _array(), "avoid": _array()}),
        "visual.wardrobe": _object({"staples": _array(), "avoid": _array()}),
        "lore.milestones": _array(milestone),
        "lore.phone_schedule": _array(phone_window),
        "lore.routine": _object({k: {"type": "STRING"} for k in (
            "weekday", "weekend", "work_or_study", "rest"
        )}),
        "niche.content_pillars": _array(pillar),
    }
    card_properties: dict[str, dict[str, Any]] = {
        "schema_version": {"type": "STRING", "enum": ["1.0"]},
        "version": {"type": "INTEGER", "minimum": 1},
        "archetype": {"type": "STRING", "enum": ["influencer"]},
    }
    for block, fields in _REQUIRED_FIELDS.items():
        properties: dict[str, dict[str, Any]] = {}
        for field in fields:
            path = f"{block}.{field}"
            if path in field_schema:
                properties[field] = field_schema[path]
            elif field in list_fields:
                properties[field] = _array()
            elif field in {"apparent_age", "posts_per_day", "stories_per_day"}:
                properties[field] = {"type": "INTEGER", **({"minimum": 18} if field == "apparent_age" else {"minimum": 0})}
            elif field == "accepts_sponsored":
                properties[field] = {"type": "BOOLEAN"}
            elif field == "caption_length":
                properties[field] = _object({"min_words": {"type": "INTEGER"}, "max_words": {"type": "INTEGER"}})
            else:
                properties[field] = {"type": "STRING"}
        card_properties[block] = _schema_object(properties, list(fields))

    card_required = ["schema_version", "version", "archetype", *_CARD_BLOCKS]
    return _schema_object(
        {
            "narrative": _schema_string(
                "História canônica completa, em português, com no máximo 100 linhas."
            ),
            "persona_card": _schema_object(card_properties, card_required),
        },
        ["narrative", "persona_card"],
    )


def build_prompt(draft: PersonaGenerationInput) -> str:
    constraints = []
    if draft.name:
        constraints.append(f"Nome completo fixo: {draft.name!r}. Preserve exatamente.")
    if draft.city:
        constraints.append(f"Cidade de moradia fixa: {draft.city!r}. Preserve exatamente.")
    if draft.age is not None:
        constraints.append(f"Idade fixa: {draft.age}. Preserve exatamente.")
    fixed = "\n".join(constraints) if constraints else "Nenhum dado foi fixado pelo operador."
    return f"""Crie uma persona fictícia adulta, original e coerente para o Olimpo.

DADOS FIXOS DO OPERADOR (nunca invente outro valor para estes campos):
{fixed}

ENTREGA EM UMA ÚNICA RESPOSTA JSON:
1. `narrative`: a história-base completa, em português, com ATÉ 100 linhas.
   Descreva quem ela é, origem, idade adulta, moradia, trabalho/estudo, rotina,
   afazeres, gostos, princípios, relações, planos e limites. Explique janelas
   realistas para usar o celular: pausas tranquilas no trabalho, deslocamento,
   intervalos, noite e descanso. Não invente uso de celular durante tarefa
   perigosa, atendimento ou atividade que exija atenção total.
2. `persona_card`: card completo seguindo os blocos e campos abaixo.

REGRAS DE COERÊNCIA:
- A persona principal sempre tem 18 anos ou mais. Se o dado fixo for menor de
  18, a solicitação deve ser recusada; nunca reduza ou substitua uma idade fixa.
- A idade, a linha do tempo, a formação, o emprego e as relações precisam ser
  compatíveis entre si. Use uma só cidade principal e horários locais plausíveis.
- Faça a rotina diária e `lore.phone_schedule` concordarem. Cada janela de
  celular deve dizer dias, horário, contexto e atividades possíveis.
- Gere um perfil específico, com gostos concretos, valores, irritações, humor,
  inseguranças, opiniões, voz, nicho, formatos e limites do que não fará.
- Não use pessoa real, celebridade, endereço residencial, dados de contato ou
  identificadores de documentos. O perfil é virtual; `identity.ai_disclosure`
  deve dizer claramente isso.
- Não inclua o antigo `persona_engine_id` nem `visual.face_reference`.
- Não invente campos vazios, TODO ou placeholders. Use listas vazias somente
  quando algo realmente não se aplicar.
- `identity.apparent_age` deve ser inteiro >= 18. `identity.name`, `location.city`
  e idade devem coincidir com os dados fixos quando informados.
- Use `archetype: influencer`, `schema_version: "1.0"`, `version: 1`.
- Inclua todos estes blocos: {', '.join(_CARD_BLOCKS)}.
- A história é a base para a estrutura; não contradiga os detalhes entre elas.

COMPLETUDE MÍNIMA:
- identity: name, display_name, handle sugerido, apparent_age, gender, location
  (city/state/country), occupation, language, bio, ai_disclosure.
- voice: tone (3–5), register, slang (uses e never), caption_length, emoji,
  hashtag, 5–8 frases originais de exemplo, never_say.
- visual: descrição física canônica, estética, paleta, 3–8 cenários recorrentes,
  wardrobe e forbidden_visuals; não gerar referência facial externa.
- personality: 4–7 traits, values, irritations, moves_her, default_mood, humor,
  mood_range, insecurities e opinions.
- lore: backstory curta e causal, 3 ou mais milestones cronológicos, relações,
  pets se fizerem sentido, routine, phone_schedule detalhada e current_situation.
- niche: primary específico, 3–6 temas secondary, audience adulta, pain_points,
  3–5 content_pillars cuja share some 1.0, formats e references.
- taboos: topics, banned_words, never_interactions, sensitive_handling e
  hard_blocks claros.
- cadence: horários/dias coerentes com a rotina e as janelas de celular.
- commercial: aceita ou não publicidade; disclosure sempre explícito quando aceitar.

Responda somente com o JSON no formato solicitado. Não inclua comentários fora dele."""


def validate_generated_persona(
    output: GeneratedPersonaOutput,
    draft: PersonaGenerationInput,
) -> dict[str, Any]:
    card = output.persona_card
    if card.get("schema_version") != "1.0" or card.get("version") != 1:
        raise PersonaGenerationError("A estrutura gerada usa uma versão incompatível.")
    if card.get("archetype") != "influencer":
        raise PersonaGenerationError("A geração precisa produzir uma persona influencer.")

    for block in _CARD_BLOCKS:
        value = card.get(block)
        if not isinstance(value, dict):
            raise PersonaGenerationError(f"A resposta não trouxe o bloco {block}.")
        missing = [key for key in _REQUIRED_FIELDS[block] if key not in value]
        if missing:
            raise PersonaGenerationError(
                f"A resposta veio incompleta no bloco {block}: {', '.join(missing)}."
            )

    identity = card["identity"]
    age = identity.get("apparent_age")
    if isinstance(age, bool) or not isinstance(age, int) or age < 18:
        raise PersonaGenerationError("A persona gerada precisa ter idade adulta (18+).")
    if draft.age is not None and age != draft.age:
        raise PersonaGenerationError("A idade gerada não respeitou a idade informada.")
    if draft.name and str(identity.get("name", "")) != draft.name:
        raise PersonaGenerationError("O nome gerado não respeitou o nome informado.")
    location = identity.get("location")
    if not isinstance(location, dict) or not isinstance(location.get("city"), str):
        raise PersonaGenerationError("A resposta não trouxe a cidade da persona.")
    if draft.city and location["city"] != draft.city:
        raise PersonaGenerationError("A cidade gerada não respeitou a cidade informada.")
    if not str(identity.get("ai_disclosure", "")).strip():
        raise PersonaGenerationError("A ficha precisa identificar a persona como virtual.")

    voice = card["voice"]
    examples = voice.get("examples")
    if not isinstance(examples, list) or not 5 <= len(examples) <= 12:
        raise PersonaGenerationError("A persona precisa de 5 a 12 exemplos de voz.")
    lore = card["lore"]
    milestones = lore.get("milestones")
    if not isinstance(milestones, list) or len(milestones) < 3:
        raise PersonaGenerationError("A história precisa de pelo menos 3 marcos cronológicos.")
    windows = lore.get("phone_schedule")
    if not isinstance(windows, list) or len(windows) < 3:
        raise PersonaGenerationError("A rotina precisa de pelo menos 3 janelas de uso do celular.")
    for window in windows:
        if not isinstance(window, dict) or not all(
            str(window.get(field, "")).strip()
            for field in ("days", "start", "end", "context", "phone_activities")
        ):
            raise PersonaGenerationError("Uma janela de celular veio sem horário ou contexto.")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(window["start"])) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", str(window["end"])
        ):
            raise PersonaGenerationError("Os horários de uso do celular precisam estar em HH:MM.")
    pillars = card["niche"].get("content_pillars")
    if not isinstance(pillars, list) or not pillars:
        raise PersonaGenerationError("O nicho precisa definir os pilares de conteúdo.")
    try:
        share = sum(float(item["share"]) for item in pillars)
    except (KeyError, TypeError, ValueError) as exc:
        raise PersonaGenerationError("Os pilares precisam informar a proporção de cada tema.") from exc
    if not 0.95 <= share <= 1.05:
        raise PersonaGenerationError("A proporção dos pilares de conteúdo precisa somar 1.")

    if "face_reference" in card["visual"]:
        raise PersonaGenerationError("A resposta trouxe campos antigos de referência facial.")
    if not str(card["visual"].get("canonical_description", "")).strip():
        raise PersonaGenerationError("Falta a descrição visual canônica.")

    # Preserve the full story used to create the card, so edits can be traced
    # back to the generation source instead of losing its details.
    lore["canonical_narrative"] = output.narrative
    return card


async def generate_persona(
    draft: PersonaGenerationInput,
) -> tuple[GeneratedPersonaOutput, dict[str, int]]:
    if not settings.gemini_api_key.strip():
        raise PersonaGenerationError(
            "Configure GEMINI_API_KEY para gerar personas.", status_code=503
        )
    if draft.age is not None and draft.age < 18:
        raise PersonaGenerationError("A idade mínima de uma persona é 18 anos.")

    request_body = {
        "systemInstruction": {
            "parts": [{
                "text": (
                    "Você cria personas ficcionais virtuais completas para um sistema de conteúdo. "
                    "Siga os dados fixos e as validações de coerência. Não gere pessoa menor de 18 anos."
                )
            }]
        },
        "contents": [{"role": "user", "parts": [{"text": build_prompt(draft)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema(),
            "maxOutputTokens": settings.persona_generation_max_output_tokens,
            "temperature": 0.7,
            "candidateCount": 1,
        },
    }
    # Gemini 3 contabiliza tokens de raciocínio dentro do mesmo teto da saída.
    # O nível padrão pode consumir parte do limite antes do JSON completo; `low`
    # preserva raciocínio suficiente para coerência e libera tokens para a ficha.
    if settings.gemini_persona_model.casefold().startswith("gemini-3"):
        request_body["generationConfig"]["thinkingConfig"] = {
            "thinkingLevel": "LOW",
            "includeThoughts": False,
        }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_persona_model}:generateContent"
    )
    payload: dict[str, Any] | None = None
    transient_statuses = {500, 502, 503, 504}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            for attempt in range(4):
                try:
                    response = await client.post(
                        url,
                        headers={"x-goog-api-key": settings.gemini_api_key.strip()},
                        json=request_body,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    break
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status not in transient_statuses or attempt == 3:
                        log.warning(
                            "persona.gemini_rejected",
                            status_code=status,
                            model=settings.gemini_persona_model,
                            attempts=attempt + 1,
                        )
                        if status == 429:
                            raise PersonaGenerationError(
                                "O Gemini atingiu o limite de chamadas. Tente mais tarde.",
                                status_code=429,
                            ) from exc
                        if status in (401, 403):
                            raise PersonaGenerationError(
                                "O Gemini recusou a chave configurada.", status_code=502
                            ) from exc
                        raise PersonaGenerationError(
                            "O serviço de geração está temporariamente indisponível. Tente novamente em alguns minutos.",
                            status_code=503 if status in transient_statuses else 502,
                        ) from exc
                    delay = 1.0 * (2 ** attempt)
                    log.info(
                        "persona.gemini_retry",
                        status_code=status,
                        attempt=attempt + 1,
                        delay_seconds=delay,
                    )
                    await asyncio.sleep(delay)
    except httpx.HTTPError as exc:
        log.warning("persona.gemini_unavailable", error_type=type(exc).__name__)
        raise PersonaGenerationError(
            "Não foi possível conectar ao Gemini. Tente novamente em instantes.",
            status_code=503,
        ) from exc

    if payload is None:
        raise PersonaGenerationError(
            "O serviço de geração está temporariamente indisponível.", status_code=503
        )

    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback") or {}
        reason = feedback.get("blockReason")
        if reason:
            log.warning("persona.gemini_prompt_blocked", block_reason=str(reason))
            raise PersonaGenerationError(
                "O Gemini bloqueou o pedido. Revise os dados informados e tente novamente."
            )
        raise PersonaGenerationError("O Gemini não retornou uma resposta para a persona.")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"}:
        log.warning("persona.gemini_candidate_blocked", finish_reason=finish_reason)
        raise PersonaGenerationError(
            "O Gemini bloqueou a resposta gerada. Tente novamente com outros dados."
        )
    if finish_reason == "MAX_TOKENS":
        usage_raw = payload.get("usageMetadata") or {}
        output_tokens = usage_raw.get("candidatesTokenCount", "desconhecido")
        raise PersonaGenerationError(
            f"O Gemini interrompeu a resposta ao atingir o limite de tokens ({output_tokens}). "
            "Nenhuma persona foi salva. Tente novamente; o modelo agora usa menos tokens de raciocínio."
        )
    parts = (candidate.get("content") or {}).get("parts") or []
    raw = "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and not part.get("thought")
    )
    try:
        generated = GeneratedPersonaOutput.model_validate_json(raw)
        validate_generated_persona(generated, draft)
    except (ValidationError, json.JSONDecodeError, PersonaGenerationError) as exc:
        if isinstance(exc, PersonaGenerationError):
            log.warning(
                "persona.gemini_output_rejected",
                model=settings.gemini_persona_model,
                reason=str(exc)[:240],
            )
            raise
        validation_errors = (
            exc.errors(include_input=False) if isinstance(exc, ValidationError) else []
        )
        log.warning(
            "persona.gemini_output_invalid",
            model=settings.gemini_persona_model,
            output_tokens=(payload.get("usageMetadata") or {}).get("candidatesTokenCount"),
            error_type=type(exc).__name__,
            validation_errors=validation_errors[:12],
        )
        raise PersonaGenerationError(
            "A resposta do Gemini não passou na validação. Nenhuma persona foi salva."
        ) from exc

    usage_raw = payload.get("usageMetadata") or {}
    usage = {
        "input_tokens": int(usage_raw.get("promptTokenCount", 0)),
        "output_tokens": int(usage_raw.get("candidatesTokenCount", 0)),
        "total_tokens": int(usage_raw.get("totalTokenCount", 0)),
    }
    log.info(
        "persona.gemini_generated",
        model=settings.gemini_persona_model,
        **usage,
        narrative_lines=len(generated.narrative.splitlines()),
    )
    return generated, usage

