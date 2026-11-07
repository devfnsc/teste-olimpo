"""API do Olimpo — consumida pelo painel e pelos webhooks do orchestrator."""

from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from olimpo.api.routers import accounts, appruncloud_inventory, media, nodes, servers
from olimpo.core.config import settings
from olimpo.core.db import healthcheck

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    log.info(
        "olimpo.starting",
        env=settings.olimpo_env,
        dispatch_enabled=settings.dispatch_enabled,
        kill_switch=settings.global_kill_switch,
    )
    if not settings.dispatch_enabled:
        log.warning(
            "dry_run.active",
            msg="DISPATCH_ENABLED=false — nada será enviado ao orchestrator",
            dir=settings.dryrun_dir,
        )
    yield
    log.info("olimpo.stopping")


app = FastAPI(
    title="Olimpo",
    description="Core de agentes sociais autônomos",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_api(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """Protege os dados e operações da API quando há token configurado.

    Ambientes fora do desenvolvimento falham fechados: sem API_TOKEN, /v1
    não atende chamadas. O painel usa um proxy same-origin e mantém o token
    somente no servidor Next.js.
    """
    if request.url.path.startswith("/v1/"):
        token = settings.api_token.strip()
        if settings.olimpo_env != "development" and not token:
            return JSONResponse(
                {"detail": "API_TOKEN precisa ser configurado fora do desenvolvimento."},
                status_code=503,
            )
        if token:
            authorization = request.headers.get("authorization", "")
            supplied = authorization.removeprefix("Bearer ").strip()
            if not authorization.startswith("Bearer ") or not hmac.compare_digest(
                supplied.encode("utf-8"), token.encode("utf-8")
            ):
                return JSONResponse({"detail": "Credencial inválida."}, status_code=401)
    return await call_next(request)


@app.get("/health", tags=["sistema"])
async def health() -> dict[str, Any]:
    """Usado pelo healthcheck do Docker e pelo painel.

    Os dois interruptores são expostos de propósito: o painel mostra uma
    faixa de aviso quando o sistema está em dry-run ou parado, e essa
    informação muda o significado de tudo o que aparece na tela.
    """
    db_ok = await healthcheck()
    return {
        "status": "ok" if db_ok else "degraded",
        "env": settings.olimpo_env,
        "database": "ok" if db_ok else "unreachable",
        "dispatch_enabled": settings.dispatch_enabled,
        "kill_switch": settings.global_kill_switch,
    }


@app.get("/metrics", tags=["sistema"], include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(servers.router)
app.include_router(appruncloud_inventory.router)
app.include_router(media.router)
app.include_router(media.marcas_router)
app.include_router(nodes.router)
app.include_router(accounts.router)

# Routers das próximas fases — ver docs/fases/
# campaigns, approvals, tasks, events (SSE)
#
# Não haverá router de webhook: o android-orchestrator não tem callback.
# O caminho é polling — ver ADR-0011.

