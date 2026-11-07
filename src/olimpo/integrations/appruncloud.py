"""Cliente mínimo da AppRunCloud para inventário e identidade Instagram.

Esta integração é paralela ao android-orchestrator. Ela implementa somente
operações de leitura/identidade confirmadas no OpenAPI da AppRunCloud e não
participa do despacho de ações existente.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID


class AppRunCloudError(Exception):
    """Erro base da integração AppRunCloud."""


class AppRunCloudConfigurationError(AppRunCloudError):
    """Configuração obrigatória ausente ou inválida."""


class AppRunCloudValidationError(AppRunCloudError):
    """Parâmetro da chamada fora do formato esperado."""


class AppRunCloudTransportError(AppRunCloudError):
    """Falha de rede antes de obter uma resposta HTTP."""


class AppRunCloudTimeoutError(AppRunCloudTransportError):
    """A chamada excedeu o timeout configurado."""


class AppRunCloudResponseError(AppRunCloudError):
    """A API respondeu fora do contrato esperado."""


class AppRunCloudHTTPError(AppRunCloudError):
    """Resposta HTTP de erro da AppRunCloud."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(f"AppRunCloud HTTP {status_code}: {message}")
        self.status_code = status_code
        self.error = error
        self.hint = hint


class AppRunCloudBadRequestError(AppRunCloudHTTPError):
    """HTTP 400: parâmetro ausente ou inválido."""


# Compatibilidade com o nome publicado na primeira versão da integração.
AppRunCloudBadRequest = AppRunCloudBadRequestError


class AppRunCloudAuthenticationError(AppRunCloudHTTPError):
    """HTTP 401: chave Bearer ausente ou inválida."""


class AppRunCloudAuthorizationError(AppRunCloudHTTPError):
    """HTTP 403: instância fora do escopo da chave."""


_TRACE_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{8,64}\Z")


def _validate_uuid(value: str, name: str) -> str:
    """Aceita UUID no formato textual canônico exigido pelo OpenAPI."""
    normalized = value.strip()
    try:
        parsed = UUID(normalized)
    except (AttributeError, ValueError) as exc:
        raise AppRunCloudValidationError(f"{name} deve ser um UUID válido") from exc
    if str(parsed) != normalized.lower():
        raise AppRunCloudValidationError(f"{name} deve ser um UUID válido")
    return normalized


@dataclass(frozen=True, slots=True)
class AppRunCloudConfig:
    """Configuração carregada exclusivamente de ``APPRUNCLOUD_*``."""

    base_url: str = "https://www.appruncloud.com"
    api_key: str = ""
    org_id: str = ""
    instance_id: str = ""
    account: str = ""
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise AppRunCloudConfigurationError(
                "APPRUNCLOUD_TIMEOUT deve ser finito e maior que zero"
            )
        parsed_url = urlsplit(self.base_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise AppRunCloudConfigurationError(
                "APPRUNCLOUD_BASE_URL deve ser HTTPS e não conter credenciais, "
                "query ou fragmento"
            )
        try:
            if self.org_id:
                _validate_uuid(self.org_id, "APPRUNCLOUD_ORG_ID")
            if self.instance_id:
                _validate_uuid(self.instance_id, "APPRUNCLOUD_INSTANCE_ID")
        except AppRunCloudValidationError as exc:
            raise AppRunCloudConfigurationError(str(exc)) from exc

    @classmethod
    def from_env(cls) -> AppRunCloudConfig:
        raw_timeout = os.getenv("APPRUNCLOUD_TIMEOUT", "30")
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise AppRunCloudConfigurationError(
                "APPRUNCLOUD_TIMEOUT deve ser numérico"
            ) from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise AppRunCloudConfigurationError(
                "APPRUNCLOUD_TIMEOUT deve ser finito e maior que zero"
            )
        org_id = os.getenv("APPRUNCLOUD_ORG_ID", "")
        instance_id = os.getenv("APPRUNCLOUD_INSTANCE_ID", "")
        return cls(
            base_url=os.getenv(
                "APPRUNCLOUD_BASE_URL", "https://www.appruncloud.com"
            ).rstrip("/"),
            api_key=os.getenv("APPRUNCLOUD_API_KEY", ""),
            org_id=org_id,
            instance_id=instance_id,
            account=os.getenv("APPRUNCLOUD_ACCOUNT", ""),
            timeout=timeout,
        )


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """Resposta HTTP mínima para permitir transporte mockado sem rede."""

    status_code: int
    body: bytes = b""


class AppRunCloudTransport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None,
        json_body: Mapping[str, Any] | None,
        timeout: float,
    ) -> TransportResponse: ...


class AppRunCloudBackend(Protocol):
    """Superfície inicial consumível sem acoplar ao cliente concreto."""

    async def get_instances(self) -> dict[str, Any]: ...

    async def account(self, instance_id: str | None = None) -> dict[str, Any]: ...

    async def instagram_accounts(self, instance_id: str | None = None) -> dict[str, Any]: ...

    async def device(self, instance_id: str | None = None) -> dict[str, Any]: ...

    async def instagram_whoami(
        self,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def like(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def save(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def comment(
        self,
        media: str,
        text: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def follow(
        self,
        user: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def unfollow(
        self,
        user: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def direct_send(
        self,
        text: str,
        *,
        to: str | None = None,
        thread: str | None = None,
        instance_id: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def photo_upload(
        self,
        file: str,
        caption: str,
        instance_id: str | None = None,
        *,
        location: str | None = None,
        usertags: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def video_upload(
        self,
        file: str,
        caption: str,
        instance_id: str | None = None,
        *,
        thumbnail: str | None = None,
        location: str | None = None,
        usertags: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def album_upload(
        self,
        files: Sequence[str],
        caption: str,
        instance_id: str | None = None,
        *,
        location: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def reel_upload(
        self,
        file: str,
        caption: str,
        instance_id: str | None = None,
        *,
        thumbnail: str | None = None,
        location: str | None = None,
        usertags: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def photo_story(
        self,
        file: str,
        instance_id: str | None = None,
        *,
        caption: str | None = None,
        mentions: str | None = None,
        links: str | None = None,
        hashtags: str | None = None,
        locations: str | None = None,
        medias: str | None = None,
        stickers: str | None = None,
        polls: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def video_story(
        self,
        file: str,
        instance_id: str | None = None,
        *,
        caption: str | None = None,
        thumbnail: str | None = None,
        mentions: str | None = None,
        links: str | None = None,
        hashtags: str | None = None,
        locations: str | None = None,
        medias: str | None = None,
        stickers: str | None = None,
        polls: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def account_insights(
        self,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def media_insights(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def media_info(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def user_stories(
        self,
        user: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def story_seen(
        self,
        story_ids: Sequence[str],
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def reels_feed(
        self,
        amount: int | None = None,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def browse_reels(
        self, instance_id: str | None = None, *, count: int | float | None = None,
        like_pct: int | float | None = None, max_likes: int | float | None = None,
        max_reposts: int | float | None = None, max_seconds: int | float | None = None,
        repost_pct: int | float | None = None, watch_min: int | float | None = None,
        watch_max: int | float | None = None, auto_start: bool | None = None,
    ) -> dict[str, Any]: ...

    async def search_and_watch(
        self, query: str, instance_id: str | None = None, *,
        count: int | float | None = None, like_pct: int | float | None = None,
        max_likes: int | float | None = None, max_reposts: int | float | None = None,
        max_seconds: int | float | None = None, repost_pct: int | float | None = None,
        watch_min: int | float | None = None, watch_max: int | float | None = None,
        auto_start: bool | None = None,
    ) -> dict[str, Any]: ...

    async def device_run(
        self, run_id: str, instance_id: str | None = None
    ) -> dict[str, Any]: ...

    async def cancel_device_run(
        self, run_id: str, instance_id: str | None = None
    ) -> dict[str, Any]: ...


class _HttpxTransport:
    """Transporte real, importado sob demanda para facilitar testes isolados."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None,
        json_body: Mapping[str, Any] | None,
        timeout: float,
    ) -> TransportResponse:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=dict(headers),
                    params=dict(params) if params else None,
                    json=dict(json_body) if json_body is not None else None,
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError from exc
        except httpx.RequestError as exc:
            raise ConnectionError(str(exc)) from exc
        return TransportResponse(status_code=response.status_code, body=response.content)


class AppRunCloudClient:
    """Cliente das operações iniciais confirmadas pelo OpenAPI."""

    def __init__(
        self,
        config: AppRunCloudConfig | None = None,
        *,
        transport: AppRunCloudTransport | None = None,
    ) -> None:
        self.config = config or AppRunCloudConfig.from_env()
        self._transport = transport or _HttpxTransport()

    def _headers(self) -> dict[str, str]:
        api_key = self._required(self.config.api_key, "APPRUNCLOUD_API_KEY")
        if not api_key.startswith("ark_"):
            raise AppRunCloudConfigurationError(
                "APPRUNCLOUD_API_KEY deve ser uma chave ark_"
            )
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def _instance_id(self, override: str | None) -> str:
        instance_id = self._required(
            override if override is not None else self.config.instance_id,
            "APPRUNCLOUD_INSTANCE_ID",
        )
        return _validate_uuid(instance_id, "APPRUNCLOUD_INSTANCE_ID")

    def _org_id(self) -> str:
        value = self._required(self.config.org_id, "APPRUNCLOUD_ORG_ID")
        return _validate_uuid(value, "APPRUNCLOUD_ORG_ID")

    @staticmethod
    def _required_field(value: str | None, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AppRunCloudValidationError(f"{name} é obrigatório")
        return value.strip()

    @staticmethod
    def _trace_fields(trace: bool | None, trace_id: str | None) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if trace is not None:
            if not isinstance(trace, bool):
                raise AppRunCloudValidationError("trace deve ser booleano")
            fields["trace"] = trace
        if trace_id is not None:
            if not isinstance(trace_id, str) or not _TRACE_ID_PATTERN.fullmatch(trace_id):
                raise AppRunCloudValidationError(
                    "trace_id deve ter de 8 a 64 letras, números ou hífens"
                )
            fields["trace_id"] = trace_id
        return fields

    async def _engage_action(
        self,
        action: str,
        fields: Mapping[str, Any],
        *,
        instance_id: str | None,
        trace: bool | None,
        trace_id: str | None,
    ) -> dict[str, Any]:
        resolved_id = self._instance_id(instance_id)
        body: dict[str, Any] = {"org_id": self._org_id(), **fields}
        body.update(self._trace_fields(trace, trace_id))
        return await self._request(
            "POST",
            f"/v1/instances/{resolved_id}/instagram/engage/{action}",
            json_body=body,
        )

    @staticmethod
    def _device_fields(
        *, count: int | float | None, like_pct: int | float | None,
        max_likes: int | float | None, max_reposts: int | float | None,
        max_seconds: int | float | None, repost_pct: int | float | None,
        watch_min: int | float | None, watch_max: int | float | None,
        auto_start: bool | None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        ranges = {
            "count": (count, 1, 100),
            "like_pct": (like_pct, 0, 100),
            "max_likes": (max_likes, 0, None),
            "max_reposts": (max_reposts, 0, None),
            "max_seconds": (max_seconds, 1, 3600),
            "repost_pct": (repost_pct, 0, 100),
            "watch_min": (watch_min, 1, 120),
            "watch_max": (watch_max, 1, 120),
        }
        for name, (value, minimum, maximum) in ranges.items():
            if value is None:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < minimum
                or (maximum is not None and value > maximum)
            ):
                bound = f"{minimum}+" if maximum is None else f"{minimum}-{maximum}"
                raise AppRunCloudValidationError(f"{name} deve estar entre {bound}")
            fields[name] = value
        if watch_min is not None and watch_max is not None and watch_min > watch_max:
            raise AppRunCloudValidationError("watch_min não pode ser maior que watch_max")
        if auto_start is not None:
            if not isinstance(auto_start, bool):
                raise AppRunCloudValidationError("auto_start deve ser booleano")
            fields["auto_start"] = auto_start
        return fields

    @staticmethod
    def _required(value: str, name: str) -> str:
        value = value.strip()
        if not value:
            raise AppRunCloudConfigurationError(f"{name} não configurada")
        return value

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = self._required(self.config.base_url, "APPRUNCLOUD_BASE_URL")
        try:
            response = await self._transport.request(
                method,
                f"{base_url.rstrip('/')}{path}",
                headers=self._headers(),
                params=params,
                json_body=json_body,
                timeout=self.config.timeout,
            )
        except AppRunCloudError:
            raise
        except TimeoutError as exc:
            raise AppRunCloudTimeoutError(
                f"AppRunCloud {method} {path}: timeout após {self.config.timeout:g}s"
            ) from exc
        except Exception as exc:
            raise AppRunCloudTransportError(
                f"AppRunCloud {method} {path}: falha de transporte"
            ) from exc

        if response.status_code >= 400:
            payload = self._decode_error_object(response.body)
            self._raise_http_error(response.status_code, payload)
        if response.status_code < 200 or response.status_code >= 300:
            raise AppRunCloudHTTPError(
                response.status_code,
                "status HTTP não documentado",
            )
        payload = self._decode_object(response.body, method=method, path=path)
        if payload.get("ok") is False:
            message = self._message_from(payload, default="operação recusada")
            raise AppRunCloudResponseError(f"AppRunCloud: {message}")
        return payload

    @staticmethod
    def _decode_error_object(body: bytes) -> dict[str, Any]:
        """Erros 401/403 não têm schema de corpo e podem chegar vazios."""
        if not body:
            return {}
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _decode_object(body: bytes, *, method: str, path: str) -> dict[str, Any]:
        if not body:
            raise AppRunCloudResponseError(
                f"AppRunCloud {method} {path}: resposta JSON vazia"
            )
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppRunCloudResponseError(
                f"AppRunCloud {method} {path}: resposta não é JSON válido"
            ) from exc
        if not isinstance(payload, dict):
            raise AppRunCloudResponseError(
                f"AppRunCloud {method} {path}: resposta JSON não é objeto"
            )
        return payload

    @staticmethod
    def _message_from(payload: Mapping[str, Any], *, default: str) -> str:
        for field in ("message", "error", "hint"):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
        return default

    @classmethod
    def _raise_http_error(cls, status_code: int, payload: Mapping[str, Any]) -> None:
        message = cls._message_from(payload, default="erro sem mensagem")
        error = payload.get("error") if isinstance(payload.get("error"), str) else None
        hint = payload.get("hint") if isinstance(payload.get("hint"), str) else None
        error_type: type[AppRunCloudHTTPError] = {
            400: AppRunCloudBadRequestError,
            401: AppRunCloudAuthenticationError,
            403: AppRunCloudAuthorizationError,
        }.get(status_code, AppRunCloudHTTPError)
        raise error_type(status_code, message, error=error, hint=hint)

    async def get_instances(self) -> dict[str, Any]:
        """Lista devices e contas: ``GET /v1/instances?org_id=...``."""
        org_id = self._org_id()
        return await self._request("GET", "/v1/instances", params={"org_id": org_id})

    async def account(self, instance_id: str | None = None) -> dict[str, Any]:
        """Lê a conta ativa e normalizada da instância."""
        org_id = self._org_id()
        resolved_id = self._instance_id(instance_id)
        return await self._request(
            "GET",
            f"/v1/instances/{resolved_id}/account",
            params={"org_id": org_id},
        )

    async def instagram_accounts(self, instance_id: str | None = None) -> dict[str, Any]:
        """Lista todas as contas Instagram logadas no app da instância."""
        org_id = self._org_id()
        resolved_id = self._instance_id(instance_id)
        return await self._request(
            "GET",
            f"/v1/instances/{resolved_id}/instagram/accounts",
            params={"org_id": org_id},
        )

    async def device(self, instance_id: str | None = None) -> dict[str, Any]:
        """Lê modelo, Android, conexão e estado do dispositivo."""
        org_id = self._org_id()
        resolved_id = self._instance_id(instance_id)
        return await self._request(
            "GET",
            f"/v1/instances/{resolved_id}/device",
            params={"org_id": org_id},
        )

    async def instagram_whoami(
        self,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Confere a sessão Instagram e retorna a conta logada."""
        return await self._engage_action(
            "whoami",
            {},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def like(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Curte a mídia informada por URL, shortcode ou PK."""
        return await self._engage_action(
            "like",
            {"media": self._required_field(media, "media")},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def save(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Salva a mídia informada por URL, shortcode ou PK."""
        return await self._engage_action(
            "save",
            {"media": self._required_field(media, "media")},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def comment(
        self,
        media: str,
        text: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Publica comentário em uma mídia."""
        return await self._engage_action(
            "comment",
            {
                "media": self._required_field(media, "media"),
                "text": self._required_field(text, "text"),
            },
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def follow(
        self,
        user: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Segue o username ou user_id informado."""
        return await self._engage_action(
            "follow",
            {"user": self._required_field(user, "user")},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def unfollow(
        self,
        user: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Deixa de seguir o username ou user_id informado."""
        return await self._engage_action(
            "unfollow",
            {"user": self._required_field(user, "user")},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def direct_send(
        self,
        text: str,
        *,
        to: str | None = None,
        thread: str | None = None,
        instance_id: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Envia DM a usernames ou a uma thread, conforme o OpenAPI."""
        if (to is None) == (thread is None):
            raise AppRunCloudValidationError(
                "informe exatamente um destino: to ou thread"
            )
        fields = {"text": self._required_field(text, "text")}
        if to is not None:
            fields["to"] = self._required_field(to, "to")
        if thread is not None:
            fields["thread"] = self._required_field(thread, "thread")
        return await self._engage_action(
            "direct-send",
            fields,
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    @staticmethod
    def _optional_fields(**fields: str | None) -> dict[str, str]:
        provided = {name: value for name, value in fields.items() if value is not None}
        invalid = [name for name, value in provided.items() if not isinstance(value, str)]
        if invalid:
            raise AppRunCloudValidationError(
                f"{', '.join(invalid)} deve ser string"
            )
        return provided  # type: ignore[return-value]

    @staticmethod
    def _optional_json_fields(
        expected_types: Mapping[str, type[Any]], **fields: str | None
    ) -> dict[str, str]:
        """Valida a forma JSON sem reserializar o texto original do payload."""
        validated: dict[str, str] = {}
        for name, value in fields.items():
            if value is None:
                continue
            if not isinstance(value, str):
                raise AppRunCloudValidationError(f"{name} deve ser uma string JSON")
            try:
                decoded = json.loads(value)
            except (json.JSONDecodeError, TypeError) as exc:
                raise AppRunCloudValidationError(f"{name} deve conter JSON válido") from exc
            expected_type = expected_types[name]
            if not isinstance(decoded, expected_type):
                kind = "objeto" if expected_type is dict else "lista"
                raise AppRunCloudValidationError(f"{name} deve conter um {kind} JSON")
            validated[name] = value
        return validated

    @staticmethod
    def _required_files(files: Sequence[str]) -> str:
        if isinstance(files, (str, bytes)) or not isinstance(files, Sequence) or not files:
            raise AppRunCloudValidationError("files deve conter ao menos um arquivo")
        normalized = [AppRunCloudClient._required_field(item, "files") for item in files]
        return ",".join(normalized)

    async def photo_upload(
        self,
        file: str,
        caption: str,
        instance_id: str | None = None,
        *,
        location: str | None = None,
        usertags: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Publica foto no feed por ``engage/photo-upload``."""
        fields = {
            "file": self._required_field(file, "file"),
            "caption": self._required_field(caption, "caption"),
            **self._optional_json_fields(
                {"location": dict, "usertags": list},
                location=location,
                usertags=usertags,
            ),
        }
        return await self._engage_action(
            "photo-upload", fields, instance_id=instance_id, trace=trace, trace_id=trace_id
        )

    async def video_upload(
        self,
        file: str,
        caption: str,
        instance_id: str | None = None,
        *,
        thumbnail: str | None = None,
        location: str | None = None,
        usertags: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Publica vídeo no feed por ``engage/video-upload``."""
        fields = {
            "file": self._required_field(file, "file"),
            "caption": self._required_field(caption, "caption"),
            **self._optional_fields(
                thumbnail=thumbnail
            ),
            **self._optional_json_fields(
                {"location": dict, "usertags": list},
                location=location,
                usertags=usertags,
            ),
        }
        return await self._engage_action(
            "video-upload", fields, instance_id=instance_id, trace=trace, trace_id=trace_id
        )

    async def album_upload(
        self,
        files: Sequence[str],
        caption: str,
        instance_id: str | None = None,
        *,
        location: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Publica carrossel; serializa a sequência no campo ``files`` do OpenAPI."""
        fields = {
            "files": self._required_files(files),
            "caption": self._required_field(caption, "caption"),
            **self._optional_json_fields({"location": dict}, location=location),
        }
        return await self._engage_action(
            "album-upload", fields, instance_id=instance_id, trace=trace, trace_id=trace_id
        )

    async def reel_upload(
        self,
        file: str,
        caption: str,
        instance_id: str | None = None,
        *,
        thumbnail: str | None = None,
        location: str | None = None,
        usertags: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Publica Reel por ``engage/clip-upload``."""
        fields = {
            "file": self._required_field(file, "file"),
            "caption": self._required_field(caption, "caption"),
            **self._optional_fields(
                thumbnail=thumbnail
            ),
            **self._optional_json_fields(
                {"location": dict, "usertags": list},
                location=location,
                usertags=usertags,
            ),
        }
        return await self._engage_action(
            "clip-upload", fields, instance_id=instance_id, trace=trace, trace_id=trace_id
        )

    async def photo_story(
        self,
        file: str,
        instance_id: str | None = None,
        *,
        caption: str | None = None,
        mentions: str | None = None,
        links: str | None = None,
        hashtags: str | None = None,
        locations: str | None = None,
        medias: str | None = None,
        stickers: str | None = None,
        polls: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Publica story de foto; os campos de figurinha são strings JSON."""
        fields = {
            "file": self._required_field(file, "file"),
            **self._optional_fields(caption=caption),
            **self._optional_json_fields(
                {
                    "mentions": list,
                    "links": list,
                    "hashtags": list,
                    "locations": list,
                    "medias": list,
                    "stickers": list,
                    "polls": list,
                },
                mentions=mentions,
                links=links,
                hashtags=hashtags,
                locations=locations,
                medias=medias,
                stickers=stickers,
                polls=polls,
            ),
        }
        return await self._engage_action(
            "photo-to-story", fields, instance_id=instance_id, trace=trace, trace_id=trace_id
        )

    async def video_story(
        self,
        file: str,
        instance_id: str | None = None,
        *,
        caption: str | None = None,
        thumbnail: str | None = None,
        mentions: str | None = None,
        links: str | None = None,
        hashtags: str | None = None,
        locations: str | None = None,
        medias: str | None = None,
        stickers: str | None = None,
        polls: str | None = None,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Publica story de vídeo por ``engage/video-to-story``."""
        fields = {
            "file": self._required_field(file, "file"),
            **self._optional_fields(caption=caption, thumbnail=thumbnail),
            **self._optional_json_fields(
                {
                    "mentions": list,
                    "links": list,
                    "hashtags": list,
                    "locations": list,
                    "medias": list,
                    "stickers": list,
                    "polls": list,
                },
                mentions=mentions,
                links=links,
                hashtags=hashtags,
                locations=locations,
                medias=medias,
                stickers=stickers,
                polls=polls,
            ),
        }
        return await self._engage_action(
            "video-to-story", fields, instance_id=instance_id, trace=trace, trace_id=trace_id
        )

    async def account_insights(
        self,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Obtém métricas da conta profissional via ``engage/insights-account``."""
        return await self._engage_action(
            "insights-account",
            {},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def media_insights(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Obtém métricas de uma mídia via ``engage/insights-media``."""
        return await self._engage_action(
            "insights-media",
            {"media": self._required_field(media, "media")},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def media_info(
        self,
        media: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Obtém informações de uma mídia via ``engage/media-info``."""
        return await self._engage_action(
            "media-info",
            {"media": self._required_field(media, "media")},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def user_stories(
        self,
        user: str,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Lista stories ativos de um usuário via ``engage/user-stories``."""
        return await self._engage_action(
            "user-stories",
            {"user": self._required_field(user, "user")},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def story_seen(
        self,
        story_ids: Sequence[str],
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Marca IDs de stories como vistos via ``engage/story-seen``."""
        if isinstance(story_ids, (str, bytes)) or not isinstance(story_ids, Sequence):
            raise AppRunCloudValidationError("story_ids deve ser uma lista não vazia")
        if not story_ids:
            raise AppRunCloudValidationError("story_ids deve ser uma lista não vazia")
        normalized_ids = [
            self._required_field(story_id, "story_ids") for story_id in story_ids
        ]
        return await self._engage_action(
            "story-seen",
            {"story": ",".join(normalized_ids)},
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def reels_feed(
        self,
        amount: int | None = None,
        instance_id: str | None = None,
        *,
        trace: bool | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Consulta a lista de Reels via ``engage/reels``; não assiste Reels."""
        fields: dict[str, Any] = {}
        if amount is not None:
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise AppRunCloudValidationError("amount deve ser um inteiro positivo")
            fields["amount"] = amount
        return await self._engage_action(
            "reels",
            fields,
            instance_id=instance_id,
            trace=trace,
            trace_id=trace_id,
        )

    async def browse_reels(
        self,
        instance_id: str | None = None,
        *,
        count: int | float | None = None,
        like_pct: int | float | None = None,
        max_likes: int | float | None = None,
        max_reposts: int | float | None = None,
        max_seconds: int | float | None = None,
        repost_pct: int | float | None = None,
        watch_min: int | float | None = None,
        watch_max: int | float | None = None,
        auto_start: bool | None = None,
    ) -> dict[str, Any]:
        """Inicia fluxo assíncrono para navegar Reels via ``device/browse_reels``."""
        resolved_id = self._instance_id(instance_id)
        body = {
            "org_id": self._org_id(),
            **self._device_fields(
                count=count, like_pct=like_pct, max_likes=max_likes,
                max_reposts=max_reposts, max_seconds=max_seconds,
                repost_pct=repost_pct, watch_min=watch_min, watch_max=watch_max,
                auto_start=auto_start,
            ),
        }
        return await self._request(
            "POST", f"/v1/instances/{resolved_id}/instagram/device/browse_reels",
            json_body=body,
        )

    async def search_and_watch(
        self,
        query: str,
        instance_id: str | None = None,
        *,
        count: int | float | None = None,
        like_pct: int | float | None = None,
        max_likes: int | float | None = None,
        max_reposts: int | float | None = None,
        max_seconds: int | float | None = None,
        repost_pct: int | float | None = None,
        watch_min: int | float | None = None,
        watch_max: int | float | None = None,
        auto_start: bool | None = None,
    ) -> dict[str, Any]:
        """Busca e inicia um fluxo de Reels via ``device/search_and_watch``."""
        resolved_query = self._required_field(query, "query")
        resolved_id = self._instance_id(instance_id)
        body = {
            "org_id": self._org_id(),
            "query": resolved_query,
            **self._device_fields(
                count=count, like_pct=like_pct, max_likes=max_likes,
                max_reposts=max_reposts, max_seconds=max_seconds,
                repost_pct=repost_pct, watch_min=watch_min, watch_max=watch_max,
                auto_start=auto_start,
            ),
        }
        return await self._request(
            "POST", f"/v1/instances/{resolved_id}/instagram/device/search_and_watch",
            json_body=body,
        )

    async def device_run(
        self, run_id: str, instance_id: str | None = None
    ) -> dict[str, Any]:
        """Consulta estado e resultados do fluxo via ``GET device/run``."""
        resolved_id = self._instance_id(instance_id)
        return await self._request(
            "GET",
            f"/v1/instances/{resolved_id}/instagram/device/run",
            params={
                "org_id": self._org_id(),
                "run_id": self._required_field(run_id, "run_id"),
            },
        )

    async def cancel_device_run(
        self, run_id: str, instance_id: str | None = None
    ) -> dict[str, Any]:
        """Solicita cancelamento no próximo passo via ``POST device/run/cancel``."""
        resolved_id = self._instance_id(instance_id)
        return await self._request(
            "POST",
            f"/v1/instances/{resolved_id}/instagram/device/run/cancel",
            json_body={
                "org_id": self._org_id(),
                "run_id": self._required_field(run_id, "run_id"),
            },
        )

