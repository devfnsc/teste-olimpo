"""Consultas de leitura da central AppRunCloud.

Este router expõe somente listagem de instâncias, conta conectada e estado do
device. Não usa os métodos de ação do cliente AppRunCloud.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Query

from olimpo.integrations.appruncloud import (
    AppRunCloudClient,
    AppRunCloudConfig,
    AppRunCloudConfigurationError,
    AppRunCloudError,
    AppRunCloudHTTPError,
)

router = APIRouter(prefix="/v1/integrations/appruncloud", tags=["AppRunCloud · leitura"])
log = structlog.get_logger(__name__)

_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_API_KEY_PATTERN = re.compile(r"\bark_[A-Za-z0-9_-]+\b")


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
                422, "A AppRunCloud recusou os parâmetros ou os dados da consulta."
            ) from exc
        raise HTTPException(
            502,
            "Falha ao consultar a AppRunCloud. Tente novamente.",
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


@router.get("/instances")
async def list_instances(
    include_details: bool = False,
    detail_limit: int = Query(default=6, ge=1, le=6),
) -> dict[str, Any]:
    """Lista devices e contas vinculadas na organização configurada."""
    client = _client()
    result = await _read(client.get_instances())
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
            for attempt in range(3):
                try:
                    return await _read(operation())
                except HTTPException as exc:
                    if exc.status_code != 422 or attempt == 2:
                        raise
                    await asyncio.sleep(0.15 * (attempt + 1))
            raise RuntimeError("Consulta detalhada encerrada sem resultado")

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
        else:
            enriched["account_detail"] = account_result
        if isinstance(instagram_accounts_result, Exception):
            enriched["instagram_accounts_error"] = "consulta_indisponivel"
        else:
            enriched["instagram_accounts_detail"] = instagram_accounts_result
        if isinstance(device_result, Exception):
            enriched["device_detail_error"] = "consulta_indisponivel"
        else:
            enriched["device_detail"] = device_result
        return enriched

    result = dict(result)
    result[instances_key] = await asyncio.gather(
        *(enrich(instance) for instance in instances[:detail_limit])
    ) + instances[detail_limit:]
    return result


@router.get("/instances/{instance_id}/account")
async def get_instance_account(instance_id: UUID) -> dict:
    """Consulta qual conta está conectada à instância."""
    client = _client()
    return await _read(client.account(str(instance_id)))


@router.get("/instances/{instance_id}/instagram/accounts")
async def get_instance_instagram_accounts(instance_id: UUID) -> dict:
    """Lista todas as contas Instagram logadas no app da instância."""
    client = _client()
    return await _read(client.instagram_accounts(str(instance_id)))


@router.get("/instances/{instance_id}/device")
async def get_instance_device(instance_id: UUID) -> dict:
    """Consulta informações e estado do device."""
    client = _client()
    return await _read(client.device(str(instance_id)))

