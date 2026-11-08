"""Inventário AppRunCloud: somente leitura e detalhes com limite explícito."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from olimpo.api.routers import appruncloud_inventory as inventory
from olimpo.integrations.appruncloud import (
    AppRunCloudBadRequestError,
    AppRunCloudError,
)


class FakeClient:
    def __init__(self, count: int = 8) -> None:
        self.instances = [
            {"id": str(uuid.uuid4()), "slot": index}
            for index in range(count - 1)
        ] + [{"id": "invalid-id", "slot": count - 1}]
        self.account_calls: list[str] = []
        self.instagram_accounts_calls: list[str] = []
        self.device_calls: list[str] = []

    async def get_instances(self) -> dict[str, Any]:
        return {"ok": True, "data": self.instances}

    async def account(self, instance_id: str) -> dict[str, Any]:
        self.account_calls.append(instance_id)
        if len(self.account_calls) == 2:
            raise AppRunCloudError("account detail unavailable")
        return {"ok": True, "data": {"username": "demo"}}

    async def instagram_accounts(self, instance_id: str) -> dict[str, Any]:
        self.instagram_accounts_calls.append(instance_id)
        return {"ok": True, "data": [{"username": "demo"}, {"username": "demo.alt"}]}

    async def device(self, instance_id: str) -> dict[str, Any]:
        self.device_calls.append(instance_id)
        return {"ok": True, "data": {"status": "online"}}


@pytest.mark.asyncio
async def test_list_instances_sem_detalhes_nao_faz_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(inventory, "_client", lambda: client)

    result = await inventory.list_instances()

    assert result["data"] == client.instances
    assert client.account_calls == []
    assert client.instagram_accounts_calls == []
    assert client.device_calls == []


@pytest.mark.asyncio
async def test_detalhes_ficam_limitados_e_falha_parcial_nao_cancela_lista(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(inventory, "_client", lambda: client)

    result = await inventory.list_instances(include_details=True, detail_limit=6)
    items = result["data"]

    assert len(items) == 8
    assert len(client.account_calls) == 6
    assert len(client.instagram_accounts_calls) == 6
    assert len(client.device_calls) == 6
    assert items[0]["device_detail"]["data"]["status"] == "online"
    assert items[0]["instagram_accounts_detail"]["data"][1]["username"] == "demo.alt"
    assert items[1]["account_detail_error"] == "consulta_indisponivel"
    assert "account detail unavailable" not in str(items[1])
    assert "account_detail" not in items[6]
    assert items[7] == client.instances[7]


@pytest.mark.asyncio
async def test_detalhes_aceitam_resposta_com_chave_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()

    async def get_instances_with_instances_key() -> dict[str, Any]:
        return {"ok": True, "instances": client.instances}

    client.get_instances = get_instances_with_instances_key  # type: ignore[method-assign]
    monkeypatch.setattr(inventory, "_client", lambda: client)

    result = await inventory.list_instances(include_details=True, detail_limit=2)
    items = result["instances"]

    assert len(items) == 8
    assert len(client.account_calls) == 2
    assert len(client.instagram_accounts_calls) == 2
    assert len(client.device_calls) == 2
    assert items[0]["instagram_accounts_detail"]["data"][1]["username"] == "demo.alt"
    assert "data" not in result


@pytest.mark.asyncio
async def test_detalhe_nao_repete_rejeicao_400_e_expoe_status_sem_detalhes_sensiveis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    attempts = 0

    async def rejected(instance_id: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise AppRunCloudBadRequestError(
            400,
            "invalid app data",
            error="ig_accounts",
        )

    client.instagram_accounts = rejected  # type: ignore[method-assign]
    monkeypatch.setattr(inventory, "_client", lambda: client)

    result = await inventory.list_instances(include_details=True, detail_limit=1)
    item = result["data"][0]

    assert attempts == 1
    assert item["instagram_accounts_error"] == "consulta_indisponivel"
    assert item["instagram_accounts_upstream_status"] == 400
    assert "invalid app data" not in str(item)


@pytest.mark.asyncio
async def test_consulta_todas_as_contas_instagram_da_instancia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(inventory, "_client", lambda: client)
    instance_id = uuid.UUID(client.instances[0]["id"])

    result = await inventory.get_instance_instagram_accounts(instance_id)

    assert result["data"] == [{"username": "demo"}, {"username": "demo.alt"}]
    assert client.instagram_accounts_calls == [str(instance_id)]


@pytest.mark.asyncio
async def test_cancelamento_da_consulta_nao_vira_erro_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()

    async def cancelled_account(instance_id: str) -> dict[str, Any]:
        raise asyncio.CancelledError

    client.account = cancelled_account  # type: ignore[method-assign]
    monkeypatch.setattr(inventory, "_client", lambda: client)

    with pytest.raises(asyncio.CancelledError):
        await inventory.list_instances(include_details=True, detail_limit=1)



