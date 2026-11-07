"""Roteamento de create_task para AppRunCloud sem chamadas de rede."""

# mypy: disable-error-code="attr-defined,no-untyped-def,method-assign"

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


# O ambiente mínimo desta suíte pode não conter as dependências de infraestrutura
# usadas ao importar orchestrator.py. Os shims só fornecem símbolos de importação:
# os testes substituem request e o adaptador, portanto nenhum cliente HTTP é usado.
def _install_missing_import_shims() -> None:
    def missing(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is None
        except (ImportError, ValueError):
            return module_name not in sys.modules

    if missing("structlog"):
        class _Logger:
            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        structlog = types.ModuleType("structlog")
        structlog.get_logger = lambda *args, **kwargs: _Logger()
        sys.modules["structlog"] = structlog

    if missing("httpx"):
        httpx = types.ModuleType("httpx")

        class _HttpxError(Exception):
            pass

        class _AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, *args, **kwargs):
                raise AssertionError("rede proibida no teste de roteamento")

        httpx.TransportError = _HttpxError
        httpx.HTTPStatusError = _HttpxError
        httpx.AsyncClient = _AsyncClient
        sys.modules["httpx"] = httpx

    if missing("tenacity"):
        tenacity = types.ModuleType("tenacity")
        tenacity.retry = lambda *args, **kwargs: (lambda function: function)
        tenacity.retry_if_exception_type = lambda *args, **kwargs: object()
        tenacity.stop_after_attempt = lambda *args, **kwargs: object()
        tenacity.wait_exponential = lambda *args, **kwargs: object()
        sys.modules["tenacity"] = tenacity

    if missing("pydantic"):
        pydantic = types.ModuleType("pydantic")
        pydantic.Field = lambda default=None, **kwargs: default
        sys.modules["pydantic"] = pydantic

    if missing("pydantic_settings"):
        pydantic_settings = types.ModuleType("pydantic_settings")

        class _BaseSettings:
            pass

        pydantic_settings.BaseSettings = _BaseSettings
        pydantic_settings.SettingsConfigDict = lambda **kwargs: {}
        sys.modules["pydantic_settings"] = pydantic_settings


_install_missing_import_shims()

from olimpo.integrations.orchestrator import (  # noqa: E402
    AppRunCloudRoutingError,
    DispatchBlockedError,
    OrchestratorClient,
    build_params,
)


def fake_provider(*, response=None, error=None):
    adapter = SimpleNamespace(execute=AsyncMock())
    if error is not None:
        adapter.execute.side_effect = error
    else:
        adapter.execute.return_value = response or {"ok": True, "data": {"id": "post-1"}}
    client = SimpleNamespace(
        device_run=AsyncMock(),
        cancel_device_run=AsyncMock(),
    )
    return SimpleNamespace(
        config=SimpleNamespace(
            instance_id="00000000-0000-0000-0000-000000000002",
            account="@conta",
        ),
        adapter=adapter,
        client=client,
    )


class TestInstagramProviderRouting(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_preserva_post_tasks_e_envelope_originais(self) -> None:
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock(return_value={"id": 17, "status": "pending"})  # type: ignore[method-assign]
        params = {"target": "media-1"}

        with patch(
            "olimpo.integrations.orchestrator.create_instagram_provider", return_value=None
        ) as factory:
            result = await client.create_task(
                account="@conta",
                action="instagram.like",
                params=params,
                platform="instagram",
                priority=7,
                trace_id="trace-1234",
            )

        factory.assert_called_once_with()
        client.request.assert_awaited_once_with(
            "POST",
            "/tasks",
            {
                "action": "instagram.like",
                "account": "@conta",
                "params": {"account": "@conta", "target": "media-1"},
                "priority": 7,
            },
            trace_id="trace-1234",
        )
        self.assertEqual(result, {"id": 17, "status": "pending"})

    async def test_apprun_selecionado_recebe_action_params_e_normaliza_retorno(self) -> None:
        provider = fake_provider(response={"ok": True, "data": {"run_id": "run-9"}})
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]
        params = {"target": "media-1"}

        with (
            patch("olimpo.integrations.orchestrator.create_instagram_provider", return_value=provider),
            patch("olimpo.integrations.orchestrator.settings.dispatch_enabled", True),
            patch("olimpo.integrations.orchestrator.settings.global_kill_switch", False),
        ):
            result = await client.create_task(
                account="@conta", action="instagram.like", params=params, platform="instagram"
            )

        provider.adapter.execute.assert_awaited_once_with(
            "instagram.like", params, instance_id=provider.config.instance_id
        )
        client.request.assert_not_awaited()
        self.assertEqual(
            result,
            {
                "id": "appruncloud:run-9",
                "status": "pending",
                "ok": True,
                "data": {"run_id": "run-9"},
                "provider": "appruncloud",
            },
        )

    async def test_publish_post_com_conta_normalizada_e_sem_id_na_resposta(self) -> None:
        provider = fake_provider(response={"ok": True, "data": {"published": True}})
        provider.config.account = "  @CoNtA  "
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]
        params = build_params(
            "instagram",
            "publish_post",
            {
                "media_refs": ["photo-1", "photo-2"],
                "caption": "legenda",
                "publish": True,
            },
        )

        with (
            patch(
                "olimpo.integrations.orchestrator.create_instagram_provider",
                return_value=provider,
            ),
            patch("olimpo.integrations.orchestrator.settings.dispatch_enabled", True),
            patch("olimpo.integrations.orchestrator.settings.global_kill_switch", False),
        ):
            result = await client.create_task(
                account=" conta ",
                action="instagram.post-feed",
                params=params,
                platform="instagram",
            )

        provider.adapter.execute.assert_awaited_once_with(
            "instagram.post-feed", params, instance_id=provider.config.instance_id
        )
        client.request.assert_not_awaited()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "done")
        self.assertTrue(result["id"].startswith("appruncloud-"))

    async def test_conta_incorreta_falha_antes_do_adapter_e_da_rede(self) -> None:
        provider = fake_provider()
        provider.config.account = "@outra_conta"
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]
        params = build_params(
            "instagram",
            "publish_post",
            {
                "media_refs": ["photo-1", "photo-2"],
                "caption": "legenda",
                "publish": True,
            },
        )

        with (
            patch(
                "olimpo.integrations.orchestrator.create_instagram_provider",
                return_value=provider,
            ),
            self.assertRaisesRegex(
                AppRunCloudRoutingError, "não corresponde a APPRUNCLOUD_ACCOUNT"
            ),
        ):
            await client.create_task(
                account="@conta",
                action="instagram.post-feed",
                params=params,
                platform="instagram",
            )

        provider.adapter.execute.assert_not_awaited()
        client.request.assert_not_awaited()

    async def test_dispatche_desabilitado_grava_dry_run_sem_chamar_provedores(self) -> None:
        provider = fake_provider()
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]
        dry_run_response = {"dry_run": True, "id": "dryrun-test", "status": "verified"}
        client._record_dry_run = unittest.mock.Mock(return_value=dry_run_response)  # type: ignore[method-assign]

        with (
            patch("olimpo.integrations.orchestrator.create_instagram_provider", return_value=provider),
            patch("olimpo.integrations.orchestrator.settings.dispatch_enabled", False),
            patch("olimpo.integrations.orchestrator.settings.global_kill_switch", False),
        ):
            result = await client.create_task(
                account="@conta", action="instagram.like", params={"target": "media-1"}
            )

        self.assertEqual(result, dry_run_response)
        client._record_dry_run.assert_called_once()
        provider.adapter.execute.assert_not_awaited()
        client.request.assert_not_awaited()

    async def test_kill_switch_bloqueia_apprun_sem_tentar_legacy(self) -> None:
        provider = fake_provider()
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]

        with (
            patch("olimpo.integrations.orchestrator.create_instagram_provider", return_value=provider),
            patch("olimpo.integrations.orchestrator.settings.dispatch_enabled", True),
            patch("olimpo.integrations.orchestrator.settings.global_kill_switch", True),
            self.assertRaisesRegex(DispatchBlockedError, "GLOBAL_KILL_SWITCH"),
        ):
            await client.create_task(
                account="@conta", action="instagram.like", params={"target": "media-1"}
            )

        provider.adapter.execute.assert_not_awaited()
        client.request.assert_not_awaited()

    async def test_erro_apprun_propaga_sem_fallback_legacy_ou_rede(self) -> None:
        original_error = RuntimeError("falha AppRunCloud simulada")
        provider = fake_provider(error=original_error)
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]

        with (
            patch("olimpo.integrations.orchestrator.create_instagram_provider", return_value=provider),
            patch("olimpo.integrations.orchestrator.settings.dispatch_enabled", True),
            patch("olimpo.integrations.orchestrator.settings.global_kill_switch", False),
            self.assertRaisesRegex(RuntimeError, "falha AppRunCloud") as raised,
        ):
            await client.create_task(
                account="@conta", action="instagram.like", params={"target": "media-1"}
            )

        self.assertIs(raised.exception, original_error)
        provider.adapter.execute.assert_awaited_once()
        client.request.assert_not_awaited()

    async def test_polling_app_run_preserva_estado_e_normaliza_status_observado(self) -> None:
        provider = fake_provider()
        provider.client.device_run.return_value = {
            "ok": True,
            "data": {"state": "running", "reels_seen": 3, "likes": 1},
        }
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]
        task_id = "appruncloud:run-123"

        with patch(
            "olimpo.integrations.orchestrator.create_instagram_provider", return_value=provider
        ) as factory:
            result = await client.get_task(task_id)

        factory.assert_called_once_with("appruncloud")
        provider.client.device_run.assert_awaited_once_with(
            "run-123", instance_id=provider.config.instance_id
        )
        client.request.assert_not_awaited()
        self.assertEqual(result["id"], task_id)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["apprun_status"], "running")
        self.assertEqual(result["data"]["reels_seen"], 3)

    async def test_polling_nao_inventa_conclusao_se_app_run_nao_devolver_status(self) -> None:
        provider = fake_provider()
        provider.client.device_run.return_value = {"ok": True, "data": {"reels_seen": 2}}
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]

        with patch(
            "olimpo.integrations.orchestrator.create_instagram_provider", return_value=provider
        ):
            result = await client.get_task("appruncloud:run-456")

        self.assertNotIn("status", result)
        self.assertEqual(result["data"], {"reels_seen": 2})
        client.request.assert_not_awaited()

    async def test_cancelamento_app_run_chama_cancel_device_run(self) -> None:
        provider = fake_provider()
        provider.client.cancel_device_run.return_value = {
            "ok": True, "data": {"canceled": True}
        }
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()

        with (
            patch(
                "olimpo.integrations.orchestrator.create_instagram_provider",
                return_value=provider,
            ) as factory,
            patch("olimpo.integrations.orchestrator.settings.global_kill_switch", True),
        ):
            result = await client.cancel_task("appruncloud:run-789")

        factory.assert_called_once_with("appruncloud")
        provider.client.cancel_device_run.assert_awaited_once_with(
            "run-789", instance_id=provider.config.instance_id
        )
        self.assertEqual(result, {"ok": True, "data": {"canceled": True}})
        client.request.assert_not_awaited()

    async def test_ids_legacy_continuam_iguais_em_get_e_cancel(self) -> None:
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock(side_effect=[{"status": "running"}, {"ok": True}])  # type: ignore[method-assign]

        with patch(
            "olimpo.integrations.orchestrator.create_instagram_provider",
            side_effect=AssertionError("ID legacy não deve criar provedor AppRun"),
        ):
            got = await client.get_task("00042")
            canceled = await client.cancel_task(42)

        self.assertEqual(got, {"status": "running"})
        self.assertEqual(canceled, {"ok": True})
        self.assertEqual(
            client.request.await_args_list,
            [
                unittest.mock.call("GET", "/tasks/00042"),
                unittest.mock.call("POST", "/tasks/42/cancel"),
            ],
        )

    async def test_erro_de_poll_ou_cancel_app_run_nao_cai_no_legacy(self) -> None:
        provider = fake_provider()
        poll_error = RuntimeError("poll AppRun falhou")
        cancel_error = RuntimeError("cancel AppRun falhou")
        provider.client.device_run.side_effect = poll_error
        provider.client.cancel_device_run.side_effect = cancel_error
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()

        with patch(
            "olimpo.integrations.orchestrator.create_instagram_provider", return_value=provider
        ):
            with self.assertRaisesRegex(RuntimeError, "poll AppRun") as poll_raised:
                await client.get_task("appruncloud:run-err")
            with self.assertRaisesRegex(RuntimeError, "cancel AppRun") as cancel_raised:
                await client.cancel_task("appruncloud:run-err")

        self.assertIs(poll_raised.exception, poll_error)
        self.assertIs(cancel_raised.exception, cancel_error)
        client.request.assert_not_awaited()

    async def test_prefixo_apprun_sem_run_id_falha_antes_de_qualquer_chamada(self) -> None:
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]

        for method_name in ("get_task", "cancel_task", "task_log"):
            with self.subTest(method=method_name), patch(
                "olimpo.integrations.orchestrator.create_instagram_provider"
            ) as factory:
                method = getattr(client, method_name)
                with self.assertRaisesRegex(AppRunCloudRoutingError, "exige um run_id"):
                    await method("appruncloud:")
                factory.assert_not_called()

        client.request.assert_not_awaited()

    async def test_task_log_apprun_falha_sem_vazar_para_endpoint_legacy(self) -> None:
        client = OrchestratorClient("https://legacy.invalid", dry_run=False)
        client.request = AsyncMock()  # type: ignore[method-assign]

        with patch(
            "olimpo.integrations.orchestrator.create_instagram_provider"
        ) as factory, self.assertRaisesRegex(
            AppRunCloudRoutingError, "task_log.*não possui equivalente AppRunCloud"
        ):
            await client.task_log("appruncloud:run-logs")

        factory.assert_not_called()
        client.request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

