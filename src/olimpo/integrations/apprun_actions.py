"""Adaptador explícito das ações Instagram simples para AppRunCloud.

Os parâmetros aceitos são os produzidos por ``orchestrator.build_params``:
``target`` para mídia/usuário e ``text`` para comentário/DM. Campos sem
equivalência documentada são rejeitados para evitar perda silenciosa.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from olimpo.integrations.appruncloud import AppRunCloudBackend


class AppRunCloudActionMappingError(ValueError):
    """Ação ou parâmetro não possui tradução segura para AppRunCloud."""


class AppRunCloudActionAdapter:
    """Adaptador injetável; não cria cliente nem transporte por conta própria."""

    _QUALIFIED_ACTIONS: ClassVar[dict[str, str]] = {
        "instagram.post-feed": "publish_post",
        "instagram.post-story": "publish_story",
        "instagram.post-reel": "publish_reels",
        "instagram.watch-reels": "watch_reels",
        "instagram.watch-stories": "view_stories",
        "instagram.profile-stats": "collect_metrics",
        "instagram.doctor": "health_check",
        "instagram.save-post": "save",
        "instagram.dm": "send_dm",
        "instagram.reply": "reply_comment",
        "instagram.reel-download": "extract_content",
    }

    _FIELDS: ClassVar[dict[str, frozenset[str]]] = {
        "publish_post": frozenset({"media", "caption", "publish", "capture_id"}),
        "publish_story": frozenset({"media", "caption", "publish"}),
        "publish_reels": frozenset({"video", "caption", "publish", "audio_mode"}),
        "watch_reels": frozenset({"source", "query", "count", "watch_min", "watch_max"}),
        "view_stories": frozenset({"count"}),
        "collect_metrics": frozenset({"target"}),
        "health_check": frozenset(),
        "like": frozenset({"target"}),
        "save": frozenset({"target"}),
        "comment": frozenset({"target", "text"}),
        "follow": frozenset({"target"}),
        "unfollow": frozenset({"target"}),
        "send_dm": frozenset({"target", "text"}),
        "whoami": frozenset(),
    }

    def __init__(self, backend: AppRunCloudBackend) -> None:
        self._backend = backend

    async def execute(
        self,
        action: str,
        payload: Mapping[str, Any],
        *,
        instance_id: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Executa uma ação simples após validar o formato dos parâmetros."""
        normalized_action = self._QUALIFIED_ACTIONS.get(
            action, action.removeprefix("instagram.")
        )
        if normalized_action in {"reply_comment", "extract_content"}:
            raise AppRunCloudActionMappingError(
                f"ação Instagram explicitamente sem suporte AppRunCloud: {normalized_action}"
            )
        expected = self._FIELDS.get(normalized_action)
        if expected is None:
            raise AppRunCloudActionMappingError(
                f"ação Instagram sem equivalência AppRunCloud: {action!r}"
            )
        if not isinstance(payload, Mapping):
            raise AppRunCloudActionMappingError("payload deve ser um mapeamento")
        supplied = set(payload)
        missing = expected - supplied
        extra = supplied - expected
        if missing:
            raise AppRunCloudActionMappingError(
                f"campos obrigatórios ausentes para {normalized_action}: "
                f"{', '.join(sorted(missing))}"
            )
        if extra:
            raise AppRunCloudActionMappingError(
                f"campos sem equivalência para {normalized_action}: "
                f"{', '.join(sorted(str(field) for field in extra))}"
            )
        options: dict[str, Any] = {}
        if instance_id is not None:
            options["instance_id"] = instance_id
        if trace is not None:
            options["trace"] = trace
        if trace_id is not None:
            options["trace_id"] = trace_id

        if normalized_action == "watch_reels":
            return await self._watch_reels(payload, instance_id=instance_id, trace=trace, trace_id=trace_id)
        if normalized_action == "view_stories":
            raise AppRunCloudActionMappingError(
                "view_stories: count não identifica usuário para user_stories nem IDs para story_seen"
            )
        if normalized_action == "collect_metrics":
            target = payload["target"]
            if target is None:
                return await self._backend.account_insights(**options)
            raise AppRunCloudActionMappingError(
                "collect_metrics: target é perfil, sem equivalência a account_insights "
                "ou media_insights (que exige ID de mídia)"
            )
        if normalized_action == "health_check":
            if trace is not None or trace_id is not None:
                raise AppRunCloudActionMappingError(
                    "health_check: account não aceita trace nem trace_id"
                )
            return await self._backend.account(**({"instance_id": instance_id} if instance_id is not None else {}))
        if normalized_action == "whoami":
            return await self._backend.instagram_whoami(**options)
        if normalized_action == "publish_post":
            return await self._publish_post(payload, **options)
        if normalized_action == "publish_story":
            return await self._publish_story(payload, **options)
        if normalized_action == "publish_reels":
            return await self._publish_reels(payload, **options)
        if normalized_action in {"like", "save", "comment"}:
            media = self._required(payload, "target")
            if normalized_action == "like":
                return await self._backend.like(media, **options)
            if normalized_action == "save":
                return await self._backend.save(media, **options)
            return await self._backend.comment(
                media, self._required(payload, "text"), **options
            )
        if normalized_action in {"follow", "unfollow"}:
            user = self._required(payload, "target")
            method = self._backend.follow if normalized_action == "follow" else self._backend.unfollow
            return await method(user, **options)
        return await self._backend.direct_send(
            self._required(payload, "text"),
            to=self._required(payload, "target"),
            **options,
        )

    async def _watch_reels(
        self,
        payload: Mapping[str, Any],
        *,
        instance_id: str | None,
        trace: bool | None,
        trace_id: str | None,
    ) -> dict[str, Any]:
        if payload["source"] != "reels":
            raise AppRunCloudActionMappingError(
                "watch_reels: somente source='reels' tem equivalência confirmada"
            )
        if trace is not None or trace_id is not None:
            raise AppRunCloudActionMappingError(
                "watch_reels: rotas /instagram/device não aceitam trace nem trace_id"
            )
        options = {
            "count": payload["count"],
            "watch_min": payload["watch_min"],
            "watch_max": payload["watch_max"],
        }
        query = payload["query"]
        if query is None:
            return await self._backend.browse_reels(instance_id, **options)
        if not isinstance(query, str) or not query.strip():
            raise AppRunCloudActionMappingError(
                "watch_reels: query presente deve ser uma string não vazia"
            )
        return await self._backend.search_and_watch(
            query, instance_id, **options
        )

    async def _publish_post(
        self, payload: Mapping[str, Any], **options: Any
    ) -> dict[str, Any]:
        # build_params sempre pede capture_id=True para o caminho legacy. No
        # AppRunCloud isto é somente best-effort: validamos o contrato local,
        # mas não enviamos um campo que o OpenAPI remoto não possui e nunca
        # transformamos a ausência de ID na resposta em falha da publicação.
        if not isinstance(payload["capture_id"], bool):
            raise AppRunCloudActionMappingError(
                "publish_post: capture_id deve ser booleano"
            )
        self._require_publish(payload)
        caption = self._required(payload, "caption")
        files = payload["media"]
        if isinstance(files, (str, bytes)) or not isinstance(files, (list, tuple)):
            raise AppRunCloudActionMappingError(
                "publish_post: media deve ser lista de referências"
            )
        if len(files) < 2:
            raise AppRunCloudActionMappingError(
                "publish_post: tipo de mídia ambíguo; não é possível escolher foto ou vídeo"
            )
        normalized_files = [self._file_ref(item, "media") for item in files]
        return await self._backend.album_upload(normalized_files, caption, **options)

    async def _publish_story(
        self, payload: Mapping[str, Any], **options: Any
    ) -> dict[str, Any]:
        self._require_publish(payload)
        raise AppRunCloudActionMappingError(
            "publish_story: media não informa se o arquivo é foto ou vídeo"
        )

    async def _publish_reels(
        self, payload: Mapping[str, Any], **options: Any
    ) -> dict[str, Any]:
        self._require_publish(payload)
        audio_mode = payload["audio_mode"]
        if audio_mode != "original":
            raise AppRunCloudActionMappingError(
                "publish_reels: audio_mode não possui campo equivalente no OpenAPI"
            )
        video = self._file_ref(payload["video"], "video")
        caption = self._required(payload, "caption")
        # audio_mode=original significa manter o áudio já contido no arquivo;
        # clip-upload recebe esse próprio arquivo e não requer parâmetro extra.
        return await self._backend.reel_upload(video, caption, **options)

    @staticmethod
    def _require_publish(payload: Mapping[str, Any]) -> None:
        publish = payload["publish"]
        if not isinstance(publish, bool):
            raise AppRunCloudActionMappingError("publish deve ser booleano")
        if not publish:
            raise AppRunCloudActionMappingError(
                "publicação em rascunho não possui rota AppRunCloud equivalente"
            )

    @staticmethod
    def _file_ref(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AppRunCloudActionMappingError(
                f"{field} deve ser uma referência de arquivo não vazia"
            )
        return value

    @staticmethod
    def _required(payload: Mapping[str, Any], field: str) -> str:
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise AppRunCloudActionMappingError(
                f"{field} deve ser uma string não vazia"
            )
        return value

