"""Seleção opt-in do provedor Instagram AppRunCloud.

O retorno ``None`` significa que o chamador deve continuar usando o provedor
legacy atual. Este módulo não conecta o resultado ao dispatcher/orchestrator
e nunca troca de provedor em resposta a falhas durante uma ação.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from olimpo.integrations.apprun_actions import AppRunCloudActionAdapter
    from olimpo.integrations.appruncloud import (
        AppRunCloudClient,
        AppRunCloudConfig,
        AppRunCloudTransport,
    )


class InstagramProviderSelectionError(ValueError):
    """Nome de provedor Instagram desconhecido ou malformado."""


@dataclass(frozen=True, slots=True)
class AppRunCloudInstagramProvider:
    """Componentes AppRunCloud construídos para injeção explícita."""

    config: AppRunCloudConfig
    client: AppRunCloudClient
    adapter: AppRunCloudActionAdapter


def create_instagram_provider(
    provider: str | None = None,
    *,
    transport: AppRunCloudTransport | None = None,
) -> AppRunCloudInstagramProvider | None:
    """Cria AppRunCloud se selecionado; ``None`` preserva o fluxo legacy.

    A construção valida configuração local, mas não faz chamadas HTTP. Erros
    posteriores do AppRunCloud devem ser propagados pelo chamador, sem retry
    automático via legacy, para evitar repetir ações com efeito externo.
    """
    selected_from_environment = provider is None
    selected = os.getenv("INSTAGRAM_PROVIDER", "legacy") if provider is None else provider
    if not isinstance(selected, str):
        raise InstagramProviderSelectionError(
            "INSTAGRAM_PROVIDER deve ser 'legacy' ou 'appruncloud'"
        )
    selected = selected.strip().lower()
    if selected == "legacy":
        return None
    if selected != "appruncloud":
        raise InstagramProviderSelectionError(
            f"INSTAGRAM_PROVIDER desconhecido: {selected!r}; use 'legacy' ou 'appruncloud'"
        )

    # Imports lazy: no caminho legacy nem os componentes AppRunCloud são
    # carregados/construídos por este factory.
    from olimpo.integrations.apprun_actions import AppRunCloudActionAdapter
    from olimpo.integrations.appruncloud import (
        AppRunCloudClient,
        AppRunCloudConfig,
        AppRunCloudConfigurationError,
    )

    config = AppRunCloudConfig.from_env()
    if not config.api_key:
        raise AppRunCloudConfigurationError(
            "APPRUNCLOUD_API_KEY é obrigatória quando INSTAGRAM_PROVIDER=appruncloud"
        )
    if not config.api_key.startswith("ark_"):
        raise AppRunCloudConfigurationError(
            "APPRUNCLOUD_API_KEY deve ser uma chave ark_"
        )
    if not config.org_id:
        raise AppRunCloudConfigurationError(
            "APPRUNCLOUD_ORG_ID é obrigatória quando INSTAGRAM_PROVIDER=appruncloud"
        )
    if selected_from_environment and not config.account.strip():
        raise AppRunCloudConfigurationError(
            "APPRUNCLOUD_ACCOUNT é obrigatória quando INSTAGRAM_PROVIDER=appruncloud"
        )

    client = AppRunCloudClient(config, transport=transport)
    adapter = AppRunCloudActionAdapter(client)
    return AppRunCloudInstagramProvider(config, client, adapter)

