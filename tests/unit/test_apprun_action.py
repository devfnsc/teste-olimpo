"""Testes do adaptador de ações AppRunCloud, sem transporte/rede."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock

from olimpo.integrations.apprun_actions import (
    AppRunCloudActionAdapter,
    AppRunCloudActionMappingError,
)
from olimpo.integrations.orchestrator import build_params


class TestAppRunCloudActionAdapter(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.backend = AsyncMock()
        self.backend.like.return_value = {"ok": True, "data": {"liked": True}}
        self.backend.save.return_value = {"ok": True, "data": {"saved": True}}
        self.backend.comment.return_value = {"ok": True, "data": {"commented": True}}
        self.backend.follow.return_value = {"ok": True, "data": {"followed": True}}
        self.backend.unfollow.return_value = {"ok": True, "data": {"followed": False}}
        self.backend.direct_send.return_value = {"ok": True, "data": {"sent": True}}
        self.backend.instagram_whoami.return_value = {"ok": True, "data": {"username": "demo"}}
        self.backend.album_upload.return_value = {"ok": True, "data": {"id": "album-1"}}
        self.backend.reel_upload.return_value = {"ok": True, "data": {"id": "reel-1"}}
        self.backend.browse_reels.return_value = {"ok": True, "data": {"run_id": "r-1"}}
        self.backend.search_and_watch.return_value = {"ok": True, "data": {"run_id": "r-2"}}
        self.backend.account_insights.return_value = {"ok": True, "data": {"views": 5}}
        self.backend.media_insights.return_value = {"ok": True, "data": {"likes": 2}}
        self.backend.account.return_value = {"ok": True, "data": {"username": "demo"}}
        self.backend.user_stories.return_value = {"ok": True, "data": []}
        self.backend.story_seen.return_value = {"ok": True, "data": {"seen": True}}
        self.adapter = AppRunCloudActionAdapter(self.backend)

    async def test_mapeia_payloads_build_params_para_metodos_backend(self) -> None:
        common: dict[str, Any] = {
            "instance_id": "00000000-0000-0000-0000-000000000002",
            "trace": True,
            "trace_id": "trace-1234",
        }
        cases: list[tuple[str, dict[str, Any], str, tuple[str, ...]]] = [
            ("like", {"target": "https://instagram.invalid/p/abc"}, "like", ("https://instagram.invalid/p/abc",)),
            ("save", {"target": "shortcode"}, "save", ("shortcode",)),
            ("comment", {"target": "media-pk", "text": "olá"}, "comment", ("media-pk", "olá")),
            ("follow", {"target": "@perfil"}, "follow", ("@perfil",)),
            ("unfollow", {"target": "12345"}, "unfollow", ("12345",)),
            ("send_dm", {"target": "@destino", "text": "oi"}, "direct_send", ("oi",)),
        ]

        for action, payload, method_name, args in cases:
            with self.subTest(action=action):
                result = await self.adapter.execute(action, payload, **common)
                method = getattr(self.backend, method_name)
                method.assert_awaited_with(*args, **common, **({"to": "@destino"} if action == "send_dm" else {}))
                self.assertTrue(result["ok"])
                method.reset_mock()

    async def test_mapeia_whoami_sem_payload(self) -> None:
        result = await self.adapter.execute("instagram.whoami", {})

        self.backend.instagram_whoami.assert_awaited_once_with()
        self.assertEqual(result["data"]["username"], "demo")

    async def test_rejeita_acao_sem_equivalencia(self) -> None:
        with self.assertRaisesRegex(AppRunCloudActionMappingError, "sem equivalência"):
            await self.adapter.execute("publish_live", {})
        self.backend.assert_not_awaited()

    async def test_rejeita_campos_sem_equivalencia_e_campos_ausentes(self) -> None:
        invalid: list[tuple[str, dict[str, Any]]] = [
            ("like", {"target": "media", "publish": True}),
            ("comment", {"target": "media"}),
            ("send_dm", {"text": "oi", "target": "@x", "thread": "t-1"}),
            ("whoami", {"target": "@x"}),
        ]
        for action, payload in invalid:
            with self.subTest(action=action, payload=payload), self.assertRaises(
                AppRunCloudActionMappingError
            ):
                await self.adapter.execute(action, payload)
        self.backend.assert_not_awaited()

    async def test_rejeita_target_ou_texto_vazio_antes_do_backend(self) -> None:
        invalid: list[tuple[str, dict[str, Any]]] = [
            ("like", {"target": " "}),
            ("save", {"target": None}),
            ("comment", {"target": "media", "text": " "}),
            ("follow", {"target": 123}),
            ("send_dm", {"target": "@x", "text": ""}),
        ]
        for action, payload in invalid:
            with self.subTest(action=action), self.assertRaises(
                AppRunCloudActionMappingError
            ):
                await self.adapter.execute(action, payload)
        self.backend.assert_not_awaited()

    async def test_traduz_post_com_multiplas_midias_para_album(self) -> None:
        payload = {
            "media": ["https://cdn.invalid/one.jpg", "https://cdn.invalid/two.jpg"],
            "caption": "carrossel",
            "publish": True,
            # false não solicita a captura de ID não garantida pela rota remota.
            "capture_id": False,
        }
        result = await self.adapter.execute(
            "publish_post", payload, instance_id="00000000-0000-0000-0000-000000000002"
        )

        self.backend.album_upload.assert_awaited_once_with(
            ["https://cdn.invalid/one.jpg", "https://cdn.invalid/two.jpg"],
            "carrossel",
            instance_id="00000000-0000-0000-0000-000000000002",
        )
        self.assertTrue(result["ok"])

    async def test_publish_post_qualificado_aceita_capture_id_best_effort(self) -> None:
        payload = build_params(
            "instagram",
            "publish_post",
            {
                "media_refs": ["https://cdn.invalid/one.jpg", "https://cdn.invalid/two.jpg"],
                "caption": "carrossel real",
                "publish": True,
            },
        )

        self.assertIs(payload["capture_id"], True)
        result = await self.adapter.execute("instagram.post-feed", payload)

        self.backend.album_upload.assert_awaited_once_with(
            ["https://cdn.invalid/one.jpg", "https://cdn.invalid/two.jpg"],
            "carrossel real",
        )
        self.assertTrue(result["ok"])

    async def test_traduz_publish_reels_video_explicito_para_reel_upload(self) -> None:
        payload = {
            "video": "https://cdn.invalid/reel.mp4",
            "caption": "reel",
            "publish": True,
            "audio_mode": "original",
        }
        result = await self.adapter.execute("instagram.publish_reels", payload)

        self.backend.reel_upload.assert_awaited_once_with(
            "https://cdn.invalid/reel.mp4", "reel"
        )
        self.assertTrue(result["ok"])

    async def test_rejeita_publicacoes_ambiguas_ou_sem_equivalencia(self) -> None:
        cases: list[tuple[str, dict[str, Any], str]] = [
            (
                "publish_post",
                {"media": ["single-ref"], "caption": "texto", "publish": True, "capture_id": False},
                "ambíguo",
            ),
            (
                "publish_post",
                {"media": ["one", "two"], "caption": "texto", "publish": True, "capture_id": "true"},
                "booleano",
            ),
            (
                "publish_story",
                {"media": "story-ref", "caption": "texto", "publish": True},
                "foto ou vídeo",
            ),
            (
                "publish_reels",
                {"video": "reel.mp4", "caption": "texto", "publish": False, "audio_mode": "original"},
                "rascunho",
            ),
            (
                "publish_reels",
                {"video": "reel.mp4", "caption": "texto", "publish": True, "audio_mode": "library"},
                "audio_mode",
            ),
        ]
        for action, payload, message in cases:
            with self.subTest(action=action, payload=payload), self.assertRaisesRegex(
                AppRunCloudActionMappingError, message
            ):
                await self.adapter.execute(action, payload)
        self.backend.album_upload.assert_not_awaited()
        self.backend.reel_upload.assert_not_awaited()

    async def test_rejeita_tipo_invalido_em_refs_de_carrossel_e_reel(self) -> None:
        post = {
            "media": ["photo-ref", {"type": "video", "file": "video-ref"}],
            "caption": "texto",
            "publish": True,
            "capture_id": False,
        }
        reel = {
            "video": " ",
            "caption": "texto",
            "publish": True,
            "audio_mode": "original",
        }
        for action, payload in (("publish_post", post), ("publish_reels", reel)):
            with self.subTest(action=action), self.assertRaises(
                AppRunCloudActionMappingError
            ):
                await self.adapter.execute(action, payload)
        self.backend.album_upload.assert_not_awaited()
        self.backend.reel_upload.assert_not_awaited()

    async def test_watch_reels_mapeia_browse_ou_search_com_campos_build_params(self) -> None:
        browse_payload = {
            "source": "reels", "query": None, "count": 10,
            "watch_min": 8, "watch_max": 25,
        }
        await self.adapter.execute("watch_reels", browse_payload)
        self.backend.browse_reels.assert_awaited_once_with(
            None, count=10, watch_min=8, watch_max=25
        )

        search_payload = {
            "source": "reels", "query": "receitas", "count": 4,
            "watch_min": 3, "watch_max": 9,
        }
        await self.adapter.execute("instagram.watch_reels", search_payload)
        self.backend.search_and_watch.assert_awaited_once_with(
            "receitas", None, count=4, watch_min=3, watch_max=9
        )

    async def test_collect_metrics_sem_target_consulta_metricas_da_propria_conta(self) -> None:
        await self.adapter.execute("collect_metrics", {"target": None})
        self.backend.account_insights.assert_awaited_once_with()
        self.backend.media_insights.assert_not_awaited()

    async def test_health_check_com_payload_vazio_consulta_account(self) -> None:
        await self.adapter.execute(
            "health_check", {}, instance_id="00000000-0000-0000-0000-000000000002"
        )
        self.backend.account.assert_awaited_once_with(
            instance_id="00000000-0000-0000-0000-000000000002"
        )

    async def test_rejeita_operacoes_sem_dados_ou_equivalencia_deterministica(self) -> None:
        cases: list[tuple[str, dict[str, Any]]] = [
            ("watch_reels", {"source": "explore", "query": None, "count": 10, "watch_min": 8, "watch_max": 25}),
            ("watch_reels", {"source": "reels", "query": " ", "count": 10, "watch_min": 8, "watch_max": 25}),
            ("view_stories", {"count": 10}),
            ("collect_metrics", {"target": "@perfil"}),
            ("health_check", {"unexpected": True}),
        ]
        for action, payload in cases:
            with self.subTest(action=action), self.assertRaises(
                AppRunCloudActionMappingError
            ):
                await self.adapter.execute(action, payload)
        self.backend.browse_reels.assert_not_awaited()
        self.backend.search_and_watch.assert_not_awaited()
        self.backend.user_stories.assert_not_awaited()
        self.backend.story_seen.assert_not_awaited()
        self.backend.media_insights.assert_not_awaited()
        self.backend.account.assert_not_awaited()

    async def test_reply_comment_e_extract_content_continuam_explicitamente_sem_suporte(self) -> None:
        for action in ("reply_comment", "extract_content"):
            with self.subTest(action=action), self.assertRaisesRegex(
                AppRunCloudActionMappingError, "explicitamente sem suporte"
            ):
                await self.adapter.execute(action, {})
        self.backend.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

