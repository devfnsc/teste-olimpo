"""Consultas de leitura da central AppRunCloud.

Este router expõe somente listagem de instâncias, conta conectada e estado do
device. Não usa os métodos de ação do cliente AppRunCloud.
"""

from __future__ import annotations

import asyncio
import copy
import os
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Body, HTTPException, Query

from olimpo.integrations.appruncloud import (
    AppRunCloudClient,
    AppRunCloudConfig,
    AppRunCloudConfigurationError,
    AppRunCloudError,
    AppRunCloudHTTPError,
    AppRunCloudTransportError,
)

router = APIRouter(prefix="/v1/integrations/appruncloud", tags=["AppRunCloud · leitura"])
log = structlog.get_logger(__name__)

_INVENTORY_CACHE_TTL_SECONDS = 20
_INVENTORY_STALE_MAX_SECONDS = 300
_inventory_cache: tuple[str, float, str, dict[str, Any]] | None = None
_inventory_cache_lock = asyncio.Lock()

_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_API_KEY_PATTERN = re.compile(r"\bark_[A-Za-z0-9_-]+\b")

# These routes are only described by the preview endpoint below. They are
# never requested from AppRunCloud by that endpoint.
_PREVIEW_ACTIONS: dict[str, tuple[str, str]] = {
    "instagram_whoami": ("POST", "/v1/instances/{instance_id}/instagram/engage/whoami"),
    "like": ("POST", "/v1/instances/{instance_id}/instagram/engage/like"),
    "save": ("POST", "/v1/instances/{instance_id}/instagram/engage/save"),
    "comment": ("POST", "/v1/instances/{instance_id}/instagram/engage/comment"),
    "follow": ("POST", "/v1/instances/{instance_id}/instagram/engage/follow"),
    "unfollow": ("POST", "/v1/instances/{instance_id}/instagram/engage/unfollow"),
    "direct_send": ("POST", "/v1/instances/{instance_id}/instagram/engage/direct-send"),
    "photo_upload": ("POST", "/v1/instances/{instance_id}/instagram/engage/photo-upload"),
    "photo_upload_music": ("POST", "/v1/instances/{instance_id}/instagram/engage/photo-upload-music"),
    "video_upload": ("POST", "/v1/instances/{instance_id}/instagram/engage/video-upload"),
    "album_upload": ("POST", "/v1/instances/{instance_id}/instagram/engage/album-upload"),
    "album_upload_music": ("POST", "/v1/instances/{instance_id}/instagram/engage/album-upload-music"),
    "reel_upload": ("POST", "/v1/instances/{instance_id}/instagram/engage/clip-upload"),
    "reel_upload_music": ("POST", "/v1/instances/{instance_id}/instagram/engage/clip-upload-music"),
    "reel_upload_reel_music": ("POST", "/v1/instances/{instance_id}/instagram/engage/clip-upload-reel-music"),
    "photo_story": ("POST", "/v1/instances/{instance_id}/instagram/engage/photo-to-story"),
    "photo_story_music": ("POST", "/v1/instances/{instance_id}/instagram/engage/photo-to-story-music"),
    "video_story": ("POST", "/v1/instances/{instance_id}/instagram/engage/video-to-story"),
    "video_story_music": ("POST", "/v1/instances/{instance_id}/instagram/engage/video-to-story-music"),
    "account_insights": ("POST", "/v1/instances/{instance_id}/instagram/engage/insights-account"),
    "media_insights": ("POST", "/v1/instances/{instance_id}/instagram/engage/insights-media"),
    "media_info": ("POST", "/v1/instances/{instance_id}/instagram/engage/media-info"),
    "user_stories": ("POST", "/v1/instances/{instance_id}/instagram/engage/user-stories"),
    "story_seen": ("POST", "/v1/instances/{instance_id}/instagram/engage/story-seen"),
    "reels_feed": ("POST", "/v1/instances/{instance_id}/instagram/engage/reels"),
    "browse_reels": ("POST", "/v1/instances/{instance_id}/instagram/device/browse_reels"),
    "search_and_watch": ("POST", "/v1/instances/{instance_id}/instagram/device/search_and_watch"),
    "device_run": ("GET", "/v1/instances/{instance_id}/instagram/device/run"),
    "cancel_device_run": ("POST", "/v1/instances/{instance_id}/instagram/device/run/cancel"),
}


def _safe_upstream_detail(value: str | None) -> str | None:
    """Keep useful provider diagnostics out of logs only after redacting secrets."""
    if not value:
        return None
    detail = value[:240]
    for name in (
        "APPRUNCLOUD_API_KEY",
        "APPRUNCLOUD_ORG_ID",
        "APPRUNCLOUD_INSTANCE_ID",
    ):
        secret = os.getenv(name, "")
        if secret:
            detail = detail.replace(secret, "[redacted]")
    detail = _API_KEY_PATTERN.sub("[redacted]", detail)
    detail = _UUID_PATTERN.sub("[redacted]", detail)
    return detail


def _client() -> AppRunCloudClient:
    try:
        config = AppRunCloudConfig.from_env()
    except AppRunCloudConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not config.api_key or not config.org_id:
        raise HTTPException(
            503,
            "Configure APPRUNCLOUD_API_KEY e APPRUNCLOUD_ORG_ID para consultar o inventário.",
        )
    if not config.api_key.startswith("ark_"):
        raise HTTPException(503, "APPRUNCLOUD_API_KEY precisa ser uma chave ark_.")
    return AppRunCloudClient(config)


async def _read(operation: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    try:
        return await operation
    except AppRunCloudConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except AppRunCloudHTTPError as exc:
        log.warning(
            "appruncloud.read_rejected",
            error_type=type(exc).__name__,
            upstream_status=exc.status_code,
            upstream_error=_safe_upstream_detail(exc.error),
            upstream_hint=_safe_upstream_detail(exc.hint),
        )
        if exc.status_code == 401:
            raise HTTPException(
                401, "A AppRunCloud recusou a credencial configurada."
            ) from exc
        if exc.status_code == 403:
            raise HTTPException(
                403, "A AppRunCloud recusou o acesso à organização."
            ) from exc
        if exc.status_code == 400:
            raise HTTPException(
                422,
                "A AppRunCloud recusou os parâmetros ou os dados da consulta.",
                headers={"X-AppRunCloud-Status": "400"},
            ) from exc
        raise HTTPException(
            502,
            "Falha ao consultar a AppRunCloud. Tente novamente.",
            headers={"X-AppRunCloud-Status": str(exc.status_code)},
        ) from exc
    except AppRunCloudTransportError as exc:
        log.warning(
            "appruncloud.read_transport_failed",
            error_type=type(exc).__name__,
        )
        # Falha de transporte é temporária; marque 502 para o retry limitado.
        raise HTTPException(
            502,
            "A conexão com a AppRunCloud caiu durante a consulta. Tente novamente.",
            headers={"X-AppRunCloud-Status": "502"},
        ) from exc
    except AppRunCloudError as exc:
        log.warning(
            "appruncloud.read_failed",
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            502,
            "Falha ao consultar a AppRunCloud. Tente novamente.",
        ) from exc


async def _read_with_retry(
    operation: Callable[[], Awaitable[dict[str, Any]]],
    *,
    attempts: int = 3,
) -> dict[str, Any]:
    """Repete apenas erros transitórios identificados pela AppRunCloud."""
    transient_statuses = {429, 500, 502, 503, 504}
    for attempt in range(attempts):
        try:
            return await _read(operation())
        except HTTPException as exc:
            raw_status = (exc.headers or {}).get("X-AppRunCloud-Status")
            if attempt + 1 >= attempts or raw_status not in {str(code) for code in transient_statuses}:
                raise
            log.info(
                "appruncloud.read_retry",
                attempt=attempt + 1,
                upstream_status=int(raw_status),
            )
            await asyncio.sleep(0.25 * (2 ** attempt))
    raise RuntimeError("Consulta AppRunCloud encerrada sem resultado")


async def _read_inventory(client: AppRunCloudClient) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fresh cache curto e stale-if-error limitado para a lista de instâncias."""
    global _inventory_cache
    organization = client.config.org_id
    now = time.monotonic()

    async with _inventory_cache_lock:
        cached = _inventory_cache if _inventory_cache and _inventory_cache[0] == organization else None
        if cached and now - cached[1] <= _INVENTORY_CACHE_TTL_SECONDS:
            return copy.deepcopy(cached[3]), {
                "stale": False,
                "last_success_at": cached[2],
            }

        try:
            result = await _read_with_retry(client.get_instances)
        except HTTPException:
            if not cached or now - cached[1] > _INVENTORY_STALE_MAX_SECONDS:
                raise
            age_seconds = max(0, int(now - cached[1]))
            log.warning(
                "appruncloud.inventory_stale_served",
                stale_age_seconds=age_seconds,
            )
            return copy.deepcopy(cached[3]), {
                "stale": True,
                "age_seconds": age_seconds,
                "last_success_at": cached[2],
            }

        saved_at = datetime.now(UTC).isoformat()
        _inventory_cache = (organization, time.monotonic(), saved_at, copy.deepcopy(result))
        return result, {"stale": False, "last_success_at": saved_at}


@router.get("/instances")
async def list_instances(
    include_details: bool = False,
    detail_limit: int = Query(default=6, ge=1, le=6),
) -> dict[str, Any]:
    """Lista devices e contas vinculadas na organização configurada."""
    client = _client()
    result, cache_status = await _read_inventory(client)
    result = dict(result)
    result["inventory_status"] = cache_status
    if cache_status["stale"]:
        # Evita novas consultas detalhadas durante uma instabilidade.
        return result
    if not include_details:
        return result

    instances_key = next(
        (
            key
            for key in ("data", "instances")
            if isinstance(result.get(key), list)
        ),
        None,
    )
    if instances_key is None:
        return result
    instances = result[instances_key]
    detail_semaphore = asyncio.Semaphore(6)

    async def read_detail(
        operation: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        async with detail_semaphore:
            return await _read_with_retry(operation)

    def upstream_status(result: Any) -> int | None:
        if not isinstance(result, HTTPException):
            return None
        raw_status = (result.headers or {}).get("X-AppRunCloud-Status")
        try:
            return int(raw_status) if raw_status else None
        except ValueError:
            return None

    async def enrich(instance: Any) -> Any:
        if not isinstance(instance, dict):
            return instance
        instance_id = instance.get("id") or instance.get("instance_id")
        try:
            normalized_id = str(UUID(str(instance_id)))
        except (TypeError, ValueError):
            return instance

        account_result, instagram_accounts_result, device_result = await asyncio.gather(
            read_detail(lambda: client.account(normalized_id)),
            read_detail(lambda: client.instagram_accounts(normalized_id)),
            read_detail(lambda: client.device(normalized_id)),
            return_exceptions=True,
        )
        for detail_result in (
            account_result,
            instagram_accounts_result,
            device_result,
        ):
            if isinstance(detail_result, BaseException) and not isinstance(
                detail_result, Exception
            ):
                raise detail_result
        enriched = dict(instance)
        if isinstance(account_result, Exception):
            enriched["account_detail_error"] = "consulta_indisponivel"
            status = upstream_status(account_result)
            if status is not None:
                enriched["account_detail_upstream_status"] = status
        else:
            enriched["account_detail"] = account_result
        if isinstance(instagram_accounts_result, Exception):
            enriched["instagram_accounts_error"] = "consulta_indisponivel"
            status = upstream_status(instagram_accounts_result)
            if status is not None:
                enriched["instagram_accounts_upstream_status"] = status
        else:
            enriched["instagram_accounts_detail"] = instagram_accounts_result
        if isinstance(device_result, Exception):
            enriched["device_detail_error"] = "consulta_indisponivel"
            status = upstream_status(device_result)
            if status is not None:
                enriched["device_detail_upstream_status"] = status
        else:
            enriched["device_detail"] = device_result
        return enriched

    result = dict(result)
    result[instances_key] = await asyncio.gather(
        *(enrich(instance) for instance in instances[:detail_limit])
    ) + instances[detail_limit:]
    return result


@router.post("/actions/preview")
async def preview_action(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validates and describes a single-instance request without dispatching it."""
    if payload.get("dry_run") is not True:
        raise HTTPException(400, "A prévia exige dry_run=true.")

    operation = payload.get("operation")
    if not isinstance(operation, str) or operation not in _PREVIEW_ACTIONS:
        raise HTTPException(400, "Operação não reconhecida para prévia.")

    raw_instance_id = payload.get("instance_id")
    try:
        instance_id = str(UUID(str(raw_instance_id)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Selecione uma instância válida.") from exc

    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise HTTPException(400, "Os parâmetros devem ser um objeto JSON.")
    if {str(key).lower() for key in parameters} & {
        "org_id", "instance_id", "api_key", "authorization", "token"
    }:
        raise HTTPException(400, "Parâmetros de autenticação e destino são reservados.")

    method, path_template = _PREVIEW_ACTIONS[operation]
    path = path_template.format(instance_id=instance_id)
    preview: dict[str, Any] = {
        "method": method,
        "path": path,
    }
    if method == "GET":
        preview["query"] = parameters
    else:
        preview["body"] = {"org_id": "[omitido na prévia]", **parameters}

    return {
        "mode": "preview_only",
        "executed": False,
        "message": "Prévia gerada. Nenhuma chamada foi enviada à AppRunCloud.",
        "instance_id": instance_id,
        "operation": operation,
        "request": preview,
    }


@router.get("/instances/{instance_id}/account")
async def get_instance_account(instance_id: UUID) -> dict:
    """Consulta qual conta está conectada à instância."""
    client = _client()
    return await _read_with_retry(lambda: client.account(str(instance_id)))


@router.get("/instances/{instance_id}/instagram/accounts")
async def get_instance_instagram_accounts(instance_id: UUID) -> dict:
    """Lista todas as contas Instagram logadas no app da instância."""
    client = _client()
    return await _read_with_retry(lambda: client.instagram_accounts(str(instance_id)))


@router.get("/instances/{instance_id}/device")
async def get_instance_device(instance_id: UUID) -> dict:
    """Consulta informações e estado do device."""
    client = _client()
    return await _read_with_retry(lambda: client.device(str(instance_id)))

