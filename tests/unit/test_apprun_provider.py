"""Seleção local do provedor Instagram, sem transporte de rede."""

from __future__ import annotations

import os
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from olimpo.integrations.apprun_provider import (
    AppRunCloudInstagramProvider,
    InstagramProviderSelectionError,
    create_instagram_provider,
)
from olimpo.integrations.appruncloud import (
    AppRunCloudConfigurationError,
    TransportResponse,
)

VALID_ENV = {
    "INSTAGRAM_PROVIDER": "appruncloud",
    "APPRUNCLOUD_BASE_URL": "https://tenant.invalid",
    "APPRUNCLOUD_API_KEY": "ark_test_placeholder_only",
    "APPRUNCLOUD_ORG_ID": "00000000-0000-0000-0000-000000000001",
    "APPRUNCLOUD_INSTANCE_ID": "00000000-0000-0000-0000-000000000002",
    "APPRUNCLOUD_ACCOUNT": "@conta",
    "APPRUNCLOUD_TIMEOUT": "4.5",
}


class NoNetworkTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append({"method": method, "url": url})
        raise AssertionError("o teste não permite chamadas de transporte")


class TestAppRunCloudProvider(unittest.TestCase):
    def test_padrao_e_legacy_nao_constroem_componentes_appruncloud(self) -> None:
        from olimpo.integrations.appruncloud import AppRunCloudConfig

        with patch.dict(os.environ, {}, clear=True), patch.object(
            AppRunCloudConfig, "from_env", side_effect=AssertionError("não deve ler config")
        ):
            self.assertIsNone(create_instagram_provider())
            self.assertIsNone(create_instagram_provider("legacy"))

    def test_rejeita_valor_de_provedor_desconhecido(self) -> None:
        with patch.dict(
            os.environ, {"INSTAGRAM_PROVIDER": "outro"}, clear=True
        ), self.assertRaisesRegex(InstagramProviderSelectionError, "desconhecido"):
            create_instagram_provider()
        with self.assertRaisesRegex(InstagramProviderSelectionError, "legacy.*appruncloud"):
            create_instagram_provider(" ")

    def test_construcao_valida_injeta_cliente_e_adaptador_sem_rede(self) -> None:
        transport = NoNetworkTransport()
        with patch.dict(os.environ, VALID_ENV, clear=True):
            provider = create_instagram_provider(transport=transport)

        self.assertIsInstance(provider, AppRunCloudInstagramProvider)
        assert provider is not None
        self.assertEqual(provider.config.timeout, 4.5)
        self.assertIs(provider.adapter._backend, provider.client)
        self.assertIs(provider.client._transport, transport)
        self.assertEqual(transport.calls, [])

    def test_configuracao_invalida_falha_na_construcao(self) -> None:
        invalid = {**VALID_ENV, "APPRUNCLOUD_ORG_ID": "org-invalid"}
        with patch.dict(os.environ, invalid, clear=True), self.assertRaisesRegex(
            AppRunCloudConfigurationError, "ORG_ID.*UUID"
        ):
            create_instagram_provider()

    def test_ausencia_de_credenciais_obrigatorias_falha_sem_rede(self) -> None:
        for missing in (
            "APPRUNCLOUD_API_KEY",
            "APPRUNCLOUD_ORG_ID",
            "APPRUNCLOUD_ACCOUNT",
        ):
            env = {key: value for key, value in VALID_ENV.items() if key != missing}
            transport = NoNetworkTransport()
            with self.subTest(missing=missing), patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(AppRunCloudConfigurationError, missing):
                    create_instagram_provider(transport=transport)
                self.assertEqual(transport.calls, [])

    def test_construcao_explicita_do_lifecycle_nao_exige_conta(self) -> None:
        env = {
            key: value for key, value in VALID_ENV.items()
            if key != "APPRUNCLOUD_ACCOUNT"
        }
        transport = NoNetworkTransport()

        with patch.dict(os.environ, env, clear=True):
            provider = create_instagram_provider("appruncloud", transport=transport)

        self.assertIsInstance(provider, AppRunCloudInstagramProvider)
        self.assertEqual(transport.calls, [])

    def test_chave_com_formato_invalido_falha_antes_de_construir_cliente(self) -> None:
        env = {**VALID_ENV, "APPRUNCLOUD_API_KEY": "not-a-key"}
        transport = NoNetworkTransport()
        with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(
            AppRunCloudConfigurationError, "ark_"
        ):
            create_instagram_provider(transport=transport)
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()

