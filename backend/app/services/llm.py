"""LLM Provider service supporting Google Gemini and deterministic fake providers."""

from __future__ import annotations

import abc
import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import logger


class LLMError(Exception):
    """Exception raised for errors during LLM text generation."""


@dataclass
class LLMResponse:
    """Standardized response from an LLM provider."""

    text: str
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers."""

    @abc.abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Generate text given a system prompt and user prompt."""
        ...


class GeminiLLMProvider(LLMProvider):
    """Google Gemini REST API provider using generateContent."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not configured.")

        raw_model = model or settings.LLM_MODEL
        if not raw_model.startswith("models/"):
            self.model = f"models/{raw_model}"
        else:
            self.model = raw_model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Call Gemini REST generateContent API with backoff and error handling."""
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
                "maxOutputTokens": max_output_tokens if max_output_tokens is not None else settings.LLM_MAX_OUTPUT_TOKENS,
            },
        }

        if system_prompt and system_prompt.strip():
            body["systemInstruction"] = {
                "parts": [{"text": system_prompt.strip()}]
            }

        max_retries = 3
        backoff = 1.0

        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=body)
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if not candidates:
                            prompt_feedback = data.get("promptFeedback", {})
                            block_reason = prompt_feedback.get("blockReason", "Unknown block")
                            raise LLMError(f"Gemini LLM blocked response: {block_reason}")

                        candidate = candidates[0]
                        finish_reason = candidate.get("finishReason", "UNKNOWN")
                        parts = candidate.get("content", {}).get("parts", [])
                        if not parts:
                            raise LLMError(
                                f"Gemini LLM returned empty candidate (finishReason: {finish_reason})"
                            )

                        text = "".join(part.get("text", "") for part in parts)
                        usage = data.get("usageMetadata", {})
                        return LLMResponse(
                            text=text,
                            usage=usage,
                            model=self.model,
                        )

                    if response.status_code in (401, 403):
                        raise LLMError(
                            f"Authentication failed calling Gemini LLM API (HTTP {response.status_code}). Check GEMINI_API_KEY."
                        )

                    if response.status_code in (429, 500, 502, 503, 504):
                        retry_after_hdr = response.headers.get("Retry-After")
                        if retry_after_hdr:
                            try:
                                retry_wait = float(retry_after_hdr)
                            except ValueError:
                                retry_wait = backoff
                        else:
                            retry_wait = backoff

                        if attempt < max_retries:
                            logger.warning(
                                f"Gemini LLM API status {response.status_code}, retrying in {retry_wait:.1f}s"
                            )
                            await asyncio.sleep(retry_wait)
                            backoff *= 2.0
                            continue

                        raise LLMError(
                            f"Gemini LLM API failed with HTTP {response.status_code} after retries."
                        )

                    raise LLMError(
                        f"Gemini LLM API error HTTP {response.status_code}: {response.text}"
                    )
                except httpx.RequestError as exc:
                    if attempt < max_retries:
                        logger.warning(
                            f"Network error calling Gemini LLM API, retrying in {backoff:.1f}s"
                        )
                        await asyncio.sleep(backoff)
                        backoff *= 2.0
                        continue
                    raise LLMError(
                        f"Network error calling Gemini LLM API: {type(exc).__name__}"
                    ) from exc

        raise LLMError("Exhausted retries calling Gemini LLM API.")


class FakeLLMProvider(LLMProvider):
    """Deterministic, offline LLM provider for tests and development."""

    def __init__(
        self,
        mode: str = "default",
        custom_response: str | None = None,
        model: str = "fake-llm",
    ) -> None:
        self.mode = mode
        self.custom_response = custom_response
        self.model = model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Return deterministic responses depending on mode and prompts."""
        if self.custom_response is not None:
            return LLMResponse(
                text=self.custom_response,
                usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                model=self.model,
            )

        if self.mode == "invalid_citations":
            return LLMResponse(
                text="According to the codebase analysis, this is the explanation [S999].",
                usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                model=self.model,
            )

        if self.mode == "no_citations":
            return LLMResponse(
                text="According to the codebase analysis, this is the explanation without citations.",
                usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                model=self.model,
            )

        # Default mode: parse first source marker [S#] in user_prompt
        marker_match = re.search(r"\[S\d+\]", user_prompt)
        first_marker = marker_match.group(0) if marker_match else "[S1]"

        if "architecture" in user_prompt.lower() or "architecture" in system_prompt.lower():
            text = (
                f"# Architecture Overview\n\n"
                f"## Purpose\nThis application is a repository mapping system {first_marker}.\n\n"
                f"## Tech Stack\nFastAPI, Postgres pgvector, Redis ARQ, and React.\n\n"
                f"## Main Components\nAPI endpoints, background workers, and web frontend {first_marker}.\n\n"
                f"## How to Run\nExecute dev scripts in PowerShell."
            )
        elif "readme" in user_prompt.lower() or "readme" in system_prompt.lower():
            text = (
                f"# Project README\n\n"
                f"## Overview\nRepository cartographer platform {first_marker}.\n\n"
                f"## Features\nCodebase indexing, semantic search, and documentation generation.\n\n"
                f"## Setup\nFollow environment setup instructions."
            )
        else:
            text = f"Based on the codebase analysis, here is the answer {first_marker}."

        return LLMResponse(
            text=text,
            usage={"prompt_tokens": 15, "completion_tokens": 15, "total_tokens": 30},
            model=self.model,
        )


def get_llm_provider(provider: str | None = None) -> LLMProvider:
    """Factory creating LLM provider according to provider name or app settings."""
    chosen = (provider or settings.LLM_PROVIDER).lower()
    if chosen == "fake":
        return FakeLLMProvider()
    if chosen == "gemini":
        return GeminiLLMProvider()
    raise LLMError(f"Unsupported LLM_PROVIDER: {chosen}")
