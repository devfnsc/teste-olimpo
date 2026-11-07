"""Proteção das rotas da API usada pelo painel e pelo blueprint Render."""

import pytest
from fastapi import Request
from starlette.responses import Response

from olimpo.api.main import protect_api
from olimpo.core.config import settings


def request(path: str, authorization: str | None = None) -> Request:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("testclient", 123),
    })


@pytest.mark.asyncio
async def test_producao_sem_token_falha_fechada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "olimpo_env", "production")
    monkeypatch.setattr(settings, "api_token", "")
    chamada: list[bool] = []

    async def downstream(_request: Request) -> Response:
        chamada.append(True)
        return Response(status_code=204)

    response = await protect_api(request("/v1/overview"), downstream)

    assert response.status_code == 503
    assert chamada == []


@pytest.mark.asyncio
async def test_staging_sem_token_falha_fechada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "olimpo_env", "staging")
    monkeypatch.setattr(settings, "api_token", "")
    chamada: list[bool] = []

    async def downstream(_request: Request) -> Response:
        chamada.append(True)
        return Response(status_code=204)

    response = await protect_api(request("/v1/overview"), downstream)

    assert response.status_code == 503
    assert chamada == []


@pytest.mark.asyncio
async def test_producao_recusa_token_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "olimpo_env", "production")
    monkeypatch.setattr(settings, "api_token", "token-correto")

    async def downstream(_request: Request) -> Response:
        return Response(status_code=204)

    response = await protect_api(
        request("/v1/overview", "Bearer token-incorreto"), downstream
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_producao_aceita_token_valido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "olimpo_env", "production")
    monkeypatch.setattr(settings, "api_token", "token-correto")

    async def downstream(_request: Request) -> Response:
        return Response(status_code=204)

    response = await protect_api(
        request("/v1/overview", "Bearer token-correto"), downstream
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_desenvolvimento_sem_token_continua_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "olimpo_env", "development")
    monkeypatch.setattr(settings, "api_token", "")

    async def downstream(_request: Request) -> Response:
        return Response(status_code=204)

    response = await protect_api(request("/v1/overview"), downstream)

    assert response.status_code == 204

