"""Retries HTTP without replaying ambiguous writes."""

import httpx
import pytest

from olimpo.integrations.base import _should_retry_request


@pytest.mark.parametrize(
    ("method", "status", "headers", "expected"),
    [
        ("GET", 503, {}, True),
        ("GET", 429, {}, False),
        ("POST", 503, {}, False),
        ("POST", 503, {"Idempotency-Key": "request-1"}, True),
        ("POST", 429, {"Idempotency-Key": "request-1"}, False),
    ],
)
def test_http_status_retry_depends_on_method_and_idempotency(
    method: str,
    status: int,
    headers: dict[str, str],
    expected: bool,
) -> None:
    request = httpx.Request(method, "https://service.test/endpoint", headers=headers)
    response = httpx.Response(status, request=request)
    error = httpx.HTTPStatusError("upstream error", request=request, response=response)

    assert _should_retry_request(error) is expected


@pytest.mark.parametrize(
    ("method", "headers", "expected"),
    [
        ("GET", {}, True),
        ("POST", {}, False),
        ("POST", {"Idempotency-Key": "request-1"}, True),
    ],
)
def test_transport_retry_depends_on_idempotency(
    method: str,
    headers: dict[str, str],
    expected: bool,
) -> None:
    request = httpx.Request(method, "https://service.test/endpoint", headers=headers)
    error = httpx.ConnectError("connection failed", request=request)

    assert _should_retry_request(error) is expected

