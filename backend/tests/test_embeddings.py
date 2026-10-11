"""Unit tests for embedding providers (Gemini and Fake)."""

import math

import pytest
import respx
from httpx import Response

from app.core.config import settings
from app.services.embeddings import (
    EmbeddingError,
    FakeEmbeddingProvider,
    GeminiEmbeddingProvider,
    get_embedding_provider,
    normalize_l2,
)


def test_normalize_l2():
    v = [3.0, 4.0]
    normed = normalize_l2(v)
    assert pytest.approx(normed[0]) == 0.6
    assert pytest.approx(normed[1]) == 0.8
    assert pytest.approx(sum(x * x for x in normed)) == 1.0

    # Zero vector does not crash
    assert normalize_l2([0.0, 0.0]) == [0.0, 0.0]


@pytest.mark.asyncio
async def test_fake_embedding_provider():
    provider = FakeEmbeddingProvider(dimension=768)
    assert provider.dimension == 768

    # Query embedding
    q_vec = await provider.embed_query("search for functions")
    assert len(q_vec) == 768
    length = math.sqrt(sum(x * x for x in q_vec))
    assert pytest.approx(length, rel=1e-5) == 1.0

    # Determinism: same text yields same vector
    q_vec_2 = await provider.embed_query("search for functions")
    assert q_vec == q_vec_2

    # Different text yields different vector
    other_vec = await provider.embed_query("completely different topic")
    assert q_vec != other_vec

    # Document batching
    docs = ["doc 1 content", "doc 2 content"]
    doc_vecs = await provider.embed_documents(docs)
    assert len(doc_vecs) == 2
    assert len(doc_vecs[0]) == 768
    assert len(doc_vecs[1]) == 768


@pytest.mark.asyncio
@respx.mock
async def test_gemini_embedding_provider_documents_and_query():
    gemini_route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    ).mock(
        return_value=Response(
            200,
            json={
                "embeddings": [
                    {"values": [0.1] * 768},
                    {"values": [0.2] * 768},
                ]
            },
        )
    )

    provider = GeminiEmbeddingProvider(
        api_key="test-gemini-secret-key-12345",
        model="models/gemini-embedding-001",
        dimension=768,
        batch_size=2,
    )

    # Document embedding
    docs = ["func calculate()", "class User()"]
    embeddings = await provider.embed_documents(docs)
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 768
    assert gemini_route.called

    last_request = gemini_route.calls.last.request
    assert last_request.headers["x-goog-api-key"] == "test-gemini-secret-key-12345"
    assert "application/json" in last_request.headers["content-type"]

    import json
    body = json.loads(last_request.content)
    assert len(body["requests"]) == 2
    assert body["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert body["requests"][0]["outputDimensionality"] == 768

    # Query embedding
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    ).mock(
        return_value=Response(
            200,
            json={"embeddings": [{"values": [0.5] * 768}]},
        )
    )
    q_emb = await provider.embed_query("find user class")
    assert len(q_emb) == 768


@pytest.mark.asyncio
@respx.mock
async def test_gemini_embedding_provider_retry_on_429():
    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    )
    # First call 429, second call 200
    route.side_effect = [
        Response(429, text="Resource has been exhausted (e.g. check quota)."),
        Response(200, json={"embeddings": [{"values": [0.3] * 768}]}),
    ]

    provider = GeminiEmbeddingProvider(api_key="test-key", dimension=768)
    q_emb = await provider.embed_query("test query")
    assert len(q_emb) == 768
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_gemini_embedding_provider_auth_failure_no_secret_leak():
    secret_key = "super-confidential-secret-key-999"
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    ).mock(return_value=Response(401, text="API key not valid."))

    provider = GeminiEmbeddingProvider(api_key=secret_key, dimension=768)
    with pytest.raises(EmbeddingError) as exc_info:
        await provider.embed_query("test query")

    # Ensure secret key is NOT present in error message
    assert secret_key not in str(exc_info.value)
    assert "401" in str(exc_info.value)


def test_get_embedding_provider_factory(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "fake")
    provider = get_embedding_provider()
    assert isinstance(provider, FakeEmbeddingProvider)
