"""Shared retry, backoff, and pacing helper for Google Gemini API requests."""

from __future__ import annotations

import asyncio
import time

import httpx

from app.core.config import settings


class GeminiRateLimitBudgetExceeded(Exception):
    """Exception raised when the retry wait budget is exceeded for Gemini API calls."""

    def __init__(self, message: str, total_waited: float, chunks_saved: int = 0) -> None:
        super().__init__(message)
        self.total_waited = total_waited
        self.chunks_saved = chunks_saved


def extract_retry_delay(response: httpx.Response) -> float | None:
    """Extract retry delay in seconds from HTTP headers or Google RPC error details.

    Inspects:
    1. 'Retry-After' response header.
    2. Google RPC 'RetryInfo.retryDelay' in error response body (e.g. '21s' or '20.5s').
    """
    # 1. Header check
    retry_header = response.headers.get("Retry-After")
    if retry_header:
        try:
            return float(retry_header)
        except (ValueError, TypeError):
            pass

    # 2. JSON error body details check
    try:
        data = response.json()
        error = data.get("error", {})
        details = error.get("details", [])
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict):
                    # Check standard Google RPC RetryInfo
                    delay_val = item.get("retryDelay")
                    if delay_val is not None:
                        if isinstance(delay_val, (int, float)):
                            return float(delay_val)
                        if isinstance(delay_val, str):
                            cleaned = delay_val.strip().rstrip("sS").strip()
                            return float(cleaned)
    except Exception:
        pass

    return None


class GeminiRequestPacer:
    """Client-side rate pacer enforcing a maximum requests-per-minute interval."""

    def __init__(self, requests_per_minute: int = 30) -> None:
        self.rpm = max(1, requests_per_minute)
        self.min_interval = 60.0 / self.rpm
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def pace(self) -> None:
        """Wait if necessary to maintain request interval."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request_time = time.monotonic()


# Global pacers for embedding and LLM calls
embedding_pacer = GeminiRequestPacer(requests_per_minute=settings.EMBED_REQUESTS_PER_MINUTE)
llm_pacer = GeminiRequestPacer(requests_per_minute=30)
