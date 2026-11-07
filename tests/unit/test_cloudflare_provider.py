from __future__ import annotations

import base64

import httpx
import pytest

from olimpo.media.providers.base import GenerationRequest, MediaKind
from olimpo.media.providers.cloudflare import (
    MODEL_ID,
    CloudflareWorkersAIProvider,
    _dimensions,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"test-image"


@pytest.mark.parametrize(
    ("aspect", "expected"),
    [("1:1", (1024, 1024)), ("9:16", (576, 1024)), ("16:9", (1024, 576))],
)
def test_dimensions(aspect: str, expected: tuple[int, int]) -> None:
    assert _dimensions(aspect) == expected


@pytest.mark.asyncio
async def test_generate_uses_multipart_and_decodes_image() -> None:
    captured: dict[str, httpx.Request] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={"success": True, "result": {"image": base64.b64encode(PNG).decode()}},
        )

    provider = CloudflareWorkersAIProvider(
        "a" * 32, "token-secret", transport=httpx.MockTransport(handler)
    )
    request = GenerationRequest(
        kind=MediaKind.IMAGE,
        prompt="portrait of a fictional character",
        reference_images=[PNG],
        model=MODEL_ID,
        aspect_ratio="9:16",
        seed=12,
    )

    assets = await provider.generate(request)
    sent = captured["request"]
    payload = await sent.aread()

    assert len(assets) == 1
    assert assets[0].conteudo == PNG
    assert assets[0].mime == "image/png"
    assert assets[0].metadata == {
        "model": MODEL_ID, "seed": 12, "width": 576, "height": 1024,
    }
    assert sent.url.path.endswith(f"/accounts/{'a' * 32}/ai/run/{MODEL_ID}")
    assert sent.headers["authorization"] == "Bearer token-secret"
    assert sent.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b"portrait of a fictional character" in payload
    assert b"input_image_0" in payload


@pytest.mark.asyncio
async def test_provider_rejects_invalid_model_and_missing_credentials() -> None:
    provider = CloudflareWorkersAIProvider("", "")
    request = GenerationRequest(kind=MediaKind.IMAGE, prompt="test", model="unknown")

    assert not provider.supports(request)
    with pytest.raises(RuntimeError, match="credenciais"):
        await provider.generate(request)

