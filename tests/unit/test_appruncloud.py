"""Contrato mockado do cliente AppRunCloud; nenhuma chamada sai do processo."""

from __future__ import annotations

import json
import os
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from olimpo.integrations.appruncloud import (
    AppRunCloudAuthenticationError,
    AppRunCloudAuthorizationError,
    AppRunCloudBadRequest,
    AppRunCloudClient,
    AppRunCloudConfig,
    AppRunCloudConfigurationError,
    AppRunCloudResponseError,
    AppRunCloudTimeoutError,
    AppRunCloudValidationError,
    TransportResponse,
)


class MockTransport:
    def __init__(
        self,
        response: TransportResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or response_json({"ok": True, "data": {}})
        self.error = error
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
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": dict(params) if params else None,
                "json_body": dict(json_body) if json_body else None,
                "timeout": timeout,
            }
        )
        if self.error:
            raise self.error
        return self.response


def response_json(payload: Any, status_code: int = 200) -> TransportResponse:
    return TransportResponse(status_code, json.dumps(payload).encode())


def config(**overrides: Any) -> AppRunCloudConfig:
    values: dict[str, Any] = {
        "base_url": "https://api.invalid",
        "api_key": "ark_test_not_a_credential",
        "org_id": "00000000-0000-0000-0000-000000000001",
        "instance_id": "00000000-0000-0000-0000-000000000002",
        "timeout": 7.5,
    }
    values.update(overrides)
    return AppRunCloudConfig(**values)


class TestEnvironmentConfig(unittest.TestCase):
    def test_carrega_todas_as_variaveis_de_ambiente(self) -> None:
        environment = {
            "APPRUNCLOUD_BASE_URL": "https://tenant.invalid/",
            "APPRUNCLOUD_API_KEY": "ark_test_not_a_credential",
            "APPRUNCLOUD_ORG_ID": "00000000-0000-0000-0000-000000000001",
            "APPRUNCLOUD_INSTANCE_ID": "00000000-0000-0000-0000-000000000002",
            "APPRUNCLOUD_ACCOUNT": "@conta",
            "APPRUNCLOUD_TIMEOUT": "12.5",
        }
        with patch.dict(os.environ, environment, clear=True):
            loaded = AppRunCloudConfig.from_env()
        self.assertEqual(loaded.base_url, "https://tenant.invalid")
        self.assertEqual(loaded.api_key, environment["APPRUNCLOUD_API_KEY"])
        self.assertEqual(loaded.org_id, "00000000-0000-0000-0000-000000000001")
        self.assertEqual(loaded.instance_id, "00000000-0000-0000-0000-000000000002")
        self.assertEqual(loaded.account, "@conta")
        self.assertEqual(loaded.timeout, 12.5)
        with self.assertRaisesRegex(AppRunCloudConfigurationError, "deve ser HTTPS"):
            AppRunCloudConfig(base_url="http://tenant.invalid", api_key="ark_test")
        with self.assertRaisesRegex(AppRunCloudConfigurationError, "não conter credenciais"):
            AppRunCloudConfig(
                base_url="https://user:pass@tenant.invalid", api_key="ark_test"
            )

    def test_recusa_timeout_invalido(self) -> None:
        with patch.dict(
            os.environ, {"APPRUNCLOUD_TIMEOUT": "zero"}, clear=True
        ), self.assertRaisesRegex(AppRunCloudConfigurationError, "deve ser numérico"):
            AppRunCloudConfig.from_env()

    def test_recusa_timeout_na_configuracao_direta(self) -> None:
        for invalid_timeout in (0, float("nan"), float("inf")):
            with self.subTest(timeout=invalid_timeout), self.assertRaisesRegex(
                AppRunCloudConfigurationError, "finito e maior que zero"
            ):
                AppRunCloudConfig(timeout=invalid_timeout)

    def test_config_recusa_org_id_e_instance_id_invalidos(self) -> None:
        with self.assertRaisesRegex(AppRunCloudConfigurationError, "ORG_ID.*UUID"):
            config(org_id="org-invalida")
        with self.assertRaisesRegex(AppRunCloudConfigurationError, "INSTANCE_ID.*UUID"):
            config(instance_id="instancia-invalida")


class TestAppRunCloudClient(unittest.IsolatedAsyncioTestCase):
    async def test_get_instances_usa_query_bearer_e_timeout(self) -> None:
        transport = MockTransport(response_json({"ok": True, "data": [{"id": "i"}]}))
        client = AppRunCloudClient(config(), transport=transport)

        result = await client.get_instances()

        self.assertEqual(result["data"], [{"id": "i"}])
        self.assertEqual(
            transport.calls,
            [
                {
                    "method": "GET",
                    "url": "https://api.invalid/v1/instances",
                    "headers": {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Authorization": "Bearer ark_test_not_a_credential",
                    },
                    "params": {"org_id": config().org_id},
                    "json_body": None,
                    "timeout": 7.5,
                }
            ],
        )

    async def test_account_usa_instancia_configurada(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        await client.account()

        call = transport.calls[0]
        self.assertEqual(
            call["url"],
            f"https://api.invalid/v1/instances/{config().instance_id}/account",
        )
        self.assertEqual(call["params"], {"org_id": config().org_id})
        self.assertIsNone(call["json_body"])

    async def test_account_aceita_instance_id_uuid_valido(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        instance_id = "123e4567-e89b-12d3-a456-426614174000"

        await client.account(instance_id)

        self.assertTrue(transport.calls[0]["url"].endswith(f"/{instance_id}/account"))

    async def test_instagram_accounts_lista_contas_com_get_e_org_id(self) -> None:
        payload = {"ok": True, "data": [{"username": "demo"}, {"username": "demo.alt"}]}
        transport = MockTransport(response_json(payload))
        client = AppRunCloudClient(config(), transport=transport)

        result = await client.instagram_accounts()

        self.assertEqual(result, payload)
        self.assertEqual(transport.calls[0]["method"], "GET")
        self.assertTrue(
            transport.calls[0]["url"].endswith(
                f"/v1/instances/{config().instance_id}/instagram/accounts"
            )
        )
        self.assertEqual(transport.calls[0]["params"], {"org_id": config().org_id})
        self.assertIsNone(transport.calls[0]["json_body"])

    async def test_account_rejeita_instance_id_uuid_invalido_antes_do_transporte(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaisesRegex(AppRunCloudValidationError, "INSTANCE_ID.*UUID"):
            await client.account("instancia-invalida")
        self.assertEqual(transport.calls, [])

    async def test_instagram_whoami_envia_org_no_json(self) -> None:
        transport = MockTransport(
            response_json({"ok": True, "data": {"username": "conta"}})
        )
        client = AppRunCloudClient(config(), transport=transport)

        result = await client.instagram_whoami(trace=True, trace_id="trace-test-01")

        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertTrue(call["url"].endswith("/instagram/engage/whoami"))
        self.assertIsNone(call["params"])
        self.assertEqual(
            call["json_body"],
            {"org_id": config().org_id, "trace": True, "trace_id": "trace-test-01"},
        )
        self.assertEqual(result["data"]["username"], "conta")

    async def test_whoami_rejeita_trace_id_fora_do_formato(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaisesRegex(AppRunCloudValidationError, "trace_id"):
            await client.instagram_whoami(trace_id="trace_id_invalido")
        self.assertEqual(transport.calls, [])

    async def test_acoes_engage_usam_rotas_e_payloads_do_openapi(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        instance_id = "123e4567-e89b-12d3-a456-426614174000"
        trace_fields: dict[str, Any] = {"trace": False, "trace_id": "trace-123"}
        actions: list[tuple[Any, str, dict[str, Any]]] = [
            (
                client.like("media-pk", instance_id, **trace_fields),
                "like",
                {"media": "media-pk"},
            ),
            (
                client.save("media-shortcode", instance_id, **trace_fields),
                "save",
                {"media": "media-shortcode"},
            ),
            (
                client.comment("media-url", "comentário", instance_id, **trace_fields),
                "comment",
                {"media": "media-url", "text": "comentário"},
            ),
            (
                client.follow("@perfil", instance_id, **trace_fields),
                "follow",
                {"user": "@perfil"},
            ),
            (
                client.unfollow("user-id", instance_id, **trace_fields),
                "unfollow",
                {"user": "user-id"},
            ),
            (
                client.direct_send("oi", to="@destino", instance_id=instance_id, **trace_fields),
                "direct-send",
                {"text": "oi", "to": "@destino"},
            ),
            (
                client.direct_send("resposta", thread="thread-123", instance_id=instance_id, **trace_fields),
                "direct-send",
                {"text": "resposta", "thread": "thread-123"},
            ),
        ]

        for call, route, fields in actions:
            await call
            recorded = transport.calls[-1]
            self.assertEqual(recorded["method"], "POST")
            self.assertEqual(
                recorded["url"],
                f"https://api.invalid/v1/instances/{instance_id}/instagram/engage/{route}",
            )
            self.assertEqual(
                recorded["json_body"],
                {"org_id": config().org_id, **fields, **trace_fields},
            )
            self.assertIsNone(recorded["params"])

    async def test_acoes_engage_rejeitam_campos_obrigatorios_vazios(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        invalid_calls = [
            client.like(" "),
            client.save(""),
            client.comment("media", "  "),
            client.comment("", "texto"),
            client.follow(""),
            client.unfollow(" "),
            client.direct_send("", to="@destino"),
            client.direct_send("oi", to=" "),
            client.direct_send("oi", thread=""),
        ]

        for call in invalid_calls:
            with self.assertRaises(AppRunCloudValidationError):
                await call
        self.assertEqual(transport.calls, [])

    async def test_direct_send_exige_exatamente_um_destino(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        for call in (
            client.direct_send("oi"),
            client.direct_send("oi", to="@destino", thread="thread-123"),
        ):
            with self.assertRaisesRegex(AppRunCloudValidationError, "to ou thread"):
                await call
        self.assertEqual(transport.calls, [])

    async def test_acoes_engage_reutilizam_validacao_de_trace_id(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaisesRegex(AppRunCloudValidationError, "trace_id"):
            await client.like("media-pk", trace_id="inválido_")
        self.assertEqual(transport.calls, [])

    async def test_publicacoes_e_stories_usam_rotas_e_payloads_do_openapi(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        instance_id = "123e4567-e89b-12d3-a456-426614174000"
        common: dict[str, Any] = {
            "instance_id": instance_id,
            "trace": True,
            "trace_id": "trace-123",
        }
        actions: list[tuple[Any, str, dict[str, Any]]] = [
            (
                client.photo_upload(
                    "https://cdn.invalid/photo.jpg",
                    "legenda foto",
                    location=' { "name": "São Paulo" } ',
                    usertags=' [ { "user": { "pk": "123" } } ] ',
                    **common,
                ),
                "photo-upload",
                {
                    "file": "https://cdn.invalid/photo.jpg",
                    "caption": "legenda foto",
                    "location": ' { "name": "São Paulo" } ',
                    "usertags": ' [ { "user": { "pk": "123" } } ] ',
                },
            ),
            (
                client.video_upload(
                    "video-data",
                    "legenda vídeo",
                    thumbnail="cover-data",
                    **common,
                ),
                "video-upload",
                {"file": "video-data", "caption": "legenda vídeo", "thumbnail": "cover-data"},
            ),
            (
                client.album_upload(
                    ["photo-1", "photo-2"], "legenda carrossel", **common
                ),
                "album-upload",
                {"files": "photo-1,photo-2", "caption": "legenda carrossel"},
            ),
            (
                client.reel_upload(
                    "reel-data",
                    "legenda Reel",
                    thumbnail="reel-cover",
                    usertags="[]",
                    **common,
                ),
                "clip-upload",
                {
                    "file": "reel-data",
                    "caption": "legenda Reel",
                    "thumbnail": "reel-cover",
                    "usertags": "[]",
                },
            ),
            (
                client.photo_story(
                    "story-photo",
                    caption="texto story",
                    mentions="[]",
                    links="[]",
                    hashtags="[]",
                    locations="[]",
                    medias="[]",
                    stickers="[]",
                    polls="[]",
                    **common,
                ),
                "photo-to-story",
                {
                    "file": "story-photo",
                    "caption": "texto story",
                    "mentions": "[]",
                    "links": "[]",
                    "hashtags": "[]",
                    "locations": "[]",
                    "medias": "[]",
                    "stickers": "[]",
                    "polls": "[]",
                },
            ),
            (
                client.video_story(
                    "story-video",
                    caption="vídeo no story",
                    thumbnail="story-cover",
                    stickers="[]",
                    **common,
                ),
                "video-to-story",
                {
                    "file": "story-video",
                    "caption": "vídeo no story",
                    "thumbnail": "story-cover",
                    "stickers": "[]",
                },
            ),
        ]

        for call, route, fields in actions:
            await call
            recorded = transport.calls[-1]
            self.assertEqual(recorded["method"], "POST")
            self.assertEqual(
                recorded["url"],
                f"https://api.invalid/v1/instances/{instance_id}/instagram/engage/{route}",
            )
            self.assertEqual(
                recorded["json_body"],
                {"org_id": config().org_id, **fields, "trace": True, "trace_id": "trace-123"},
            )

    async def test_story_omite_opcionais_ausentes(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        await client.photo_story("story-photo")

        self.assertEqual(
            transport.calls[0]["json_body"],
            {"org_id": config().org_id, "file": "story-photo"},
        )

    async def test_publicacoes_rejeitam_arquivo_lista_ou_legenda_obrigatoria_vazios(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        invalid_calls = [
            client.photo_upload("", "legenda"),
            client.photo_upload("foto", " "),
            client.video_upload(" ", "legenda"),
            client.video_upload("vídeo", ""),
            client.album_upload([], "legenda"),
            client.album_upload(["foto-1", " "], "legenda"),
            client.album_upload(["foto-1"], "  "),
            client.reel_upload("", "legenda"),
            client.reel_upload("reel", ""),
            client.photo_story(" "),
            client.video_story(""),
        ]

        for call in invalid_calls:
            with self.assertRaises(AppRunCloudValidationError):
                await call
        self.assertEqual(transport.calls, [])

    async def test_publicacoes_rejeitam_opcionais_que_nao_sejam_string(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaisesRegex(AppRunCloudValidationError, "thumbnail.*string"):
            await client.video_upload("video", "legenda", thumbnail=123)  # type: ignore[arg-type]
        self.assertEqual(transport.calls, [])

    async def test_campos_json_rejeitam_sintaxe_invalida_ou_tipo_incorreto(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        invalid_calls = [
            client.photo_upload("foto", "legenda", location="{"),
            client.photo_upload("foto", "legenda", location="[]"),
            client.album_upload(["foto"], "legenda", location="null"),
            client.video_upload("video", "legenda", usertags="{}"),
            client.reel_upload("reel", "legenda", usertags="nao-json"),
            client.photo_story("story", mentions="{}"),
            client.photo_story("story", links="nao-json"),
            client.photo_story("story", hashtags='"tag"'),
            client.photo_story("story", locations="{}"),
            client.photo_story("story", medias="["),
            client.photo_story("story", stickers='{"type":"gif"}'),
            client.photo_story("story", polls="1"),
            client.video_story("story", mentions="{}"),
        ]

        for call in invalid_calls:
            with self.assertRaises(AppRunCloudValidationError):
                await call
        self.assertEqual(transport.calls, [])

    async def test_campos_json_nao_string_sao_rejeitados(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaisesRegex(AppRunCloudValidationError, "location.*string JSON"):
            await client.photo_upload(
                "foto", "legenda", location={"name": "São Paulo"}  # type: ignore[arg-type]
            )
        self.assertEqual(transport.calls, [])

    async def test_insights_e_consultas_engage_usam_rotas_e_payloads(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        instance_id = "123e4567-e89b-12d3-a456-426614174000"
        trace_fields: dict[str, Any] = {"trace": True, "trace_id": "trace-123"}
        actions: list[tuple[Any, str, dict[str, Any]]] = [
            (client.account_insights(instance_id, **trace_fields), "insights-account", {}),
            (
                client.media_insights("media-pk", instance_id, **trace_fields),
                "insights-media",
                {"media": "media-pk"},
            ),
            (
                client.media_info("media-shortcode", instance_id, **trace_fields),
                "media-info",
                {"media": "media-shortcode"},
            ),
            (
                client.user_stories("@perfil", instance_id, **trace_fields),
                "user-stories",
                {"user": "@perfil"},
            ),
            (
                client.story_seen(["story-1", "story-2"], instance_id, **trace_fields),
                "story-seen",
                {"story": "story-1,story-2"},
            ),
            (
                client.reels_feed(12, instance_id, **trace_fields),
                "reels",
                {"amount": 12},
            ),
        ]

        for call, route, fields in actions:
            await call
            recorded = transport.calls[-1]
            self.assertEqual(recorded["method"], "POST")
            self.assertEqual(
                recorded["url"],
                f"https://api.invalid/v1/instances/{instance_id}/instagram/engage/{route}",
            )
            self.assertEqual(
                recorded["json_body"],
                {"org_id": config().org_id, **fields, **trace_fields},
            )

    async def test_reels_feed_omite_amount_quando_ausente(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        await client.reels_feed()

        recorded = transport.calls[0]
        self.assertTrue(recorded["url"].endswith("/instagram/engage/reels"))
        self.assertEqual(recorded["json_body"], {"org_id": config().org_id})

    async def test_novas_consultas_rejeitam_entradas_invalidas_antes_do_transporte(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        invalid_calls = [
            client.media_insights(" "),
            client.media_info(""),
            client.user_stories("  "),
            client.story_seen([]),
            client.story_seen("story-1"),
            client.story_seen(["story-1", " "]),
            client.reels_feed(0),
            client.reels_feed(-1),
            client.reels_feed(1.5),  # type: ignore[arg-type]
            client.reels_feed(True),
            client.reels_feed(2, trace_id="trace_invalid_")
        ]

        for call in invalid_calls:
            with self.assertRaises(AppRunCloudValidationError):
                await call
        self.assertEqual(transport.calls, [])

    async def test_fluxos_device_usam_rotas_query_e_payloads_do_openapi(self) -> None:
        transport = MockTransport(response_json({"ok": True, "data": {"run_id": "r-1"}}))
        client = AppRunCloudClient(config(), transport=transport)
        instance_id = "123e4567-e89b-12d3-a456-426614174000"
        options: dict[str, Any] = {
            "count": 10,
            "like_pct": 30,
            "max_likes": 2,
            "max_reposts": 0,
            "max_seconds": 600,
            "repost_pct": 0,
            "watch_min": 3,
            "watch_max": 7,
            "auto_start": False,
        }

        await client.browse_reels(instance_id, **options)
        browse = transport.calls[-1]
        self.assertEqual(browse["method"], "POST")
        self.assertEqual(
            browse["url"],
            f"https://api.invalid/v1/instances/{instance_id}/instagram/device/browse_reels",
        )
        self.assertIsNone(browse["params"])
        self.assertEqual(browse["json_body"], {"org_id": config().org_id, **options})

        await client.search_and_watch("  receitas faceis ", instance_id, **options)
        search = transport.calls[-1]
        self.assertEqual(search["method"], "POST")
        self.assertTrue(search["url"].endswith("/instagram/device/search_and_watch"))
        self.assertEqual(
            search["json_body"],
            {"org_id": config().org_id, "query": "receitas faceis", **options},
        )

        await client.device_run("run-123", instance_id)
        status = transport.calls[-1]
        self.assertEqual(status["method"], "GET")
        self.assertTrue(status["url"].endswith("/instagram/device/run"))
        self.assertEqual(status["params"], {"org_id": config().org_id, "run_id": "run-123"})
        self.assertIsNone(status["json_body"])

        await client.cancel_device_run("run-123", instance_id)
        cancel = transport.calls[-1]
        self.assertEqual(cancel["method"], "POST")
        self.assertTrue(cancel["url"].endswith("/instagram/device/run/cancel"))
        self.assertEqual(
            cancel["json_body"], {"org_id": config().org_id, "run_id": "run-123"}
        )
        self.assertIsNone(cancel["params"])

    async def test_fluxos_device_aceitam_limites_inclusivos(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)

        await client.browse_reels(
            count=1, like_pct=0, max_likes=0, max_reposts=0, max_seconds=1,
            repost_pct=100, watch_min=1, watch_max=1, auto_start=True,
        )
        await client.search_and_watch(
            "consulta", count=100, like_pct=100, max_seconds=3600,
            watch_min=120, watch_max=120,
        )
        self.assertEqual(len(transport.calls), 2)

    async def test_fluxos_device_rejeitam_valores_invalidos_antes_do_transporte(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(), transport=transport)
        invalid_calls = [
            client.browse_reels(count=0),
            client.browse_reels(count=101),
            client.browse_reels(count=True),
            client.browse_reels(like_pct=-1),
            client.browse_reels(like_pct=100.1),
            client.browse_reels(repost_pct=-1),
            client.browse_reels(max_likes=-1),
            client.browse_reels(max_reposts=-0.1),
            client.browse_reels(max_seconds=0),
            client.browse_reels(max_seconds=3601),
            client.browse_reels(watch_min=0),
            client.browse_reels(watch_max=121),
            client.browse_reels(watch_min=8, watch_max=7),
            client.browse_reels(auto_start=1),  # type: ignore[arg-type]
            client.search_and_watch(" "),
            client.search_and_watch("query", watch_min=7, watch_max=6),
            client.device_run(" "),
            client.cancel_device_run(""),
        ]

        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(
                AppRunCloudValidationError
            ):
                await call
        self.assertEqual(transport.calls, [])

    async def test_exige_configuracao_sem_tentar_transporte(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(api_key=""), transport=transport)

        with self.assertRaisesRegex(AppRunCloudConfigurationError, "API_KEY"):
            await client.get_instances()
        self.assertEqual(transport.calls, [])

    async def test_exige_chave_no_formato_ark(self) -> None:
        transport = MockTransport()
        client = AppRunCloudClient(config(api_key="formato-invalido"), transport=transport)

        with self.assertRaisesRegex(AppRunCloudConfigurationError, "chave ark_"):
            await client.get_instances()
        self.assertEqual(transport.calls, [])

    async def test_mapeia_erro_400_com_campos_do_openapi(self) -> None:
        transport = MockTransport(
            response_json(
                {
                    "error": "invalid_parameter",
                    "message": "org_id inválido",
                    "hint": "revise",
                },
                status_code=400,
            )
        )
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaises(AppRunCloudBadRequest) as raised:
            await client.get_instances()
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.error, "invalid_parameter")
        self.assertEqual(raised.exception.hint, "revise")

    async def test_mapeia_erro_401_sem_depender_de_corpo(self) -> None:
        transport = MockTransport(TransportResponse(401))
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaises(AppRunCloudAuthenticationError) as raised:
            await client.get_instances()
        self.assertEqual(raised.exception.status_code, 401)

    async def test_mapeia_erro_403_sem_depender_de_json(self) -> None:
        transport = MockTransport(TransportResponse(403, b"forbidden"))
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaises(AppRunCloudAuthorizationError) as raised:
            await client.account()
        self.assertEqual(raised.exception.status_code, 403)

    async def test_mapeia_timeout_sem_expor_chave(self) -> None:
        transport = MockTransport(error=TimeoutError())
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaises(AppRunCloudTimeoutError) as raised:
            await client.get_instances()
        self.assertNotIn(config().api_key, str(raised.exception))
        self.assertIn("7.5s", str(raised.exception))

    async def test_recusa_resposta_que_nao_seja_objeto_json(self) -> None:
        transport = MockTransport(TransportResponse(200, b"[]"))
        client = AppRunCloudClient(config(), transport=transport)

        with self.assertRaisesRegex(AppRunCloudResponseError, "não é objeto"):
            await client.get_instances()


if __name__ == "__main__":
    unittest.main()

