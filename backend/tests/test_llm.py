"""Unit tests for LLM providers (GeminiLLMProvider with respx mocks and FakeLLMProvider)."""

import pytest
import respx
from httpx import Response

from app.services.llm import (
    FakeLLMProvider,
    GeminiLLMProvider,
    LLMError,
    get_llm_provider,
)


@pytest.mark.asyncio
async def test_fake_llm_provider_default_mode():
    """FakeLLMProvider returns grounded answer citing first marker in user prompt."""
    provider = FakeLLMProvider()
    resp = await provider.generate(
        system_prompt="System instructions",
        user_prompt="Context: [S1] and [S2]\nQuestion: What is this?",
    )
    assert "[S1]" in resp.text
    assert "Based on the codebase analysis" in resp.text
    assert resp.model == "fake-llm"


@pytest.mark.asyncio
async def test_fake_llm_provider_architecture_mode():
    """FakeLLMProvider generates structured architecture overview."""
    provider = FakeLLMProvider()
    resp = await provider.generate(
        system_prompt="Generate Architecture Overview",
        user_prompt="Repository context with [S1]",
    )
    assert "# Architecture Overview" in resp.text
    assert "## Purpose" in resp.text
    assert "## Tech Stack" in resp.text
    assert "[S1]" in resp.text


@pytest.mark.asyncio
async def test_fake_llm_provider_readme_mode():
    """FakeLLMProvider generates structured README draft."""
    provider = FakeLLMProvider()
    resp = await provider.generate(
        system_prompt="Generate README draft",
        user_prompt="Repository context with [S1]",
    )
    assert "# Project README" in resp.text
    assert "## Overview" in resp.text
    assert "## Features" in resp.text
    assert "[S1]" in resp.text


@pytest.mark.asyncio
async def test_fake_llm_provider_invalid_citations_mode():
    """FakeLLMProvider in invalid_citations mode returns non-existent marker [S999]."""
    provider = FakeLLMProvider(mode="invalid_citations")
    resp = await provider.generate(
        system_prompt="",
        user_prompt="Question with [S1]",
    )
    assert "[S999]" in resp.text


@pytest.mark.asyncio
async def test_fake_llm_provider_no_citations_mode():
    """FakeLLMProvider in no_citations mode returns response without citation markers."""
    provider = FakeLLMProvider(mode="no_citations")
    resp = await provider.generate(
        system_prompt="",
        user_prompt="Question with [S1]",
    )
    assert "[S" not in resp.text


@pytest.mark.asyncio
async def test_fake_llm_provider_custom_response():
    """FakeLLMProvider returns exact custom response when configured."""
    custom = "Exact custom answer string."
    provider = FakeLLMProvider(custom_response=custom)
    resp = await provider.generate(system_prompt="", user_prompt="")
    assert resp.text == custom


def test_get_llm_provider_factory():
    """get_llm_provider returns configured provider class or raises on unsupported."""
    fake = get_llm_provider("fake")
    assert isinstance(fake, FakeLLMProvider)

    gemini = get_llm_provider("gemini")
    assert isinstance(gemini, GeminiLLMProvider)

    with pytest.raises(LLMError, match="Unsupported LLM_PROVIDER"):
        get_llm_provider("unsupported_provider_xyz")


@pytest.mark.asyncio
async def test_gemini_llm_provider_success():
    """GeminiLLMProvider successfully calls REST API and extracts text and usage."""
    provider = GeminiLLMProvider(api_key="test-key", model="gemini-3.5-flash-lite")

    with respx.mock(base_url="https://generativelanguage.googleapis.com") as respx_mock:
        respx_mock.post(
            path__regex=r"/v1beta/models/gemini-3.5-flash-lite:generateContent"
        ).respond(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "This is the answer [S1]."}],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 20,
                    "totalTokenCount": 120,
                },
            },
        )

        resp = await provider.generate(
            system_prompt="Be concise",
            user_prompt="What is this? [S1]",
        )
        assert resp.text == "This is the answer [S1]."
        assert resp.usage.get("totalTokenCount") == 120
        assert resp.model == "models/gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_gemini_llm_provider_429_retry_success():
    """GeminiLLMProvider retries on HTTP 429 and succeeds on subsequent attempt."""
    provider = GeminiLLMProvider(api_key="test-key", model="gemini-3.5-flash-lite")

    with respx.mock(base_url="https://generativelanguage.googleapis.com") as respx_mock:
        route = respx_mock.post(
            path__regex=r"/v1beta/models/gemini-3.5-flash-lite:generateContent"
        )
        # First call: 429 with Retry-After: 0.01; Second call: 200 OK
        route.side_effect = [
            Response(429, headers={"Retry-After": "0.01"}),
            Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": "Answer after retry [S1]."}],
                                "role": "model",
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
            ),
        ]

        resp = await provider.generate(system_prompt="", user_prompt="Test [S1]")
        assert resp.text == "Answer after retry [S1]."
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_gemini_llm_provider_auth_failure():
    """GeminiLLMProvider raises clear error on HTTP 401 or 403."""
    provider = GeminiLLMProvider(api_key="invalid-key", model="gemini-3.5-flash-lite")

    with respx.mock(base_url="https://generativelanguage.googleapis.com") as respx_mock:
        respx_mock.post(
            path__regex=r"/v1beta/models/gemini-3.5-flash-lite:generateContent"
        ).respond(status_code=403, json={"error": {"message": "API key not valid"}})

        with pytest.raises(LLMError, match="Authentication failed calling Gemini LLM API"):
            await provider.generate(system_prompt="", user_prompt="Test")


@pytest.mark.asyncio
async def test_gemini_llm_provider_blocked_candidate():
    """GeminiLLMProvider handles blocked candidate gracefully."""
    provider = GeminiLLMProvider(api_key="test-key", model="gemini-3.5-flash-lite")

    with respx.mock(base_url="https://generativelanguage.googleapis.com") as respx_mock:
        respx_mock.post(
            path__regex=r"/v1beta/models/gemini-3.5-flash-lite:generateContent"
        ).respond(
            status_code=200,
            json={
                "candidates": [],
                "promptFeedback": {"blockReason": "SAFETY"},
            },
        )

        with pytest.raises(LLMError, match="Gemini LLM blocked response: SAFETY"):
            await provider.generate(system_prompt="", user_prompt="Test")


@pytest.mark.asyncio
async def test_gemini_llm_provider_empty_parts():
    """GeminiLLMProvider handles empty parts gracefully."""
    provider = GeminiLLMProvider(api_key="test-key", model="gemini-3.5-flash-lite")

    with respx.mock(base_url="https://generativelanguage.googleapis.com") as respx_mock:
        respx_mock.post(
            path__regex=r"/v1beta/models/gemini-3.5-flash-lite:generateContent"
        ).respond(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {"parts": []},
                        "finishReason": "RECITATION",
                    }
                ]
            },
        )

        with pytest.raises(LLMError, match="Gemini LLM returned empty candidate"):
            await provider.generate(system_prompt="", user_prompt="Test")
