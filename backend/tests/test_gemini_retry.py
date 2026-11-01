"""Unit tests for Gemini retry delay extraction, pacing, and budget handling."""

import httpx
import pytest

from app.services.gemini_retry import (
    GeminiRateLimitBudgetExceeded,
    GeminiRequestPacer,
    extract_retry_delay,
)


def test_extract_retry_delay_from_header():
    resp = httpx.Response(429, headers={"Retry-After": "15"})
    assert extract_retry_delay(resp) == 15.0


def test_extract_retry_delay_from_google_rpc_body():
    resp = httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "message": "Resource exhausted",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "21.5s",
                    }
                ],
            }
        },
    )
    assert extract_retry_delay(resp) == 21.5


def test_extract_retry_delay_fallback_none():
    resp = httpx.Response(500, text="Internal Server Error")
    assert extract_retry_delay(resp) is None


@pytest.mark.asyncio
async def test_gemini_request_pacer_pacing():
    pacer = GeminiRequestPacer(requests_per_minute=600)  # 10 req/s, 0.1s interval
    assert pacer.min_interval == 0.1
    await pacer.pace()
    assert pacer._last_request_time > 0


def test_rate_limit_budget_exceeded_exception():
    exc = GeminiRateLimitBudgetExceeded("Wait budget exceeded", total_waited=605.0, chunks_saved=120)
    assert exc.total_waited == 605.0
    assert exc.chunks_saved == 120
    assert "Wait budget exceeded" in str(exc)
