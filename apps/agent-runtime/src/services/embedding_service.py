"""
Embedding Service: 真实 embedding 生成 + pgvector 存储
支持 SiliconFlow OpenAI-compatible embedding API
带 retry、timeout、secret redaction
"""
import asyncio
import os
import time
from typing import Any

import httpx

from config.settings import get_settings
from utils.secret_redactor import redact_string

settings = get_settings()


class EmbeddingProvider:
    """Base embedding provider."""

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        raise NotImplementedError


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding: deterministic random vectors for testing."""

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        import random
        random.seed(42)
        dim = 1024
        return [[random.random() for _ in range(dim)] for _ in texts]


class SiliconFlowEmbeddingProvider(EmbeddingProvider):
    """SiliconFlow OpenAI-compatible embedding API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.api_key = api_key or settings.siliconflow_embedding_api_key
        self.base_url = base_url or settings.siliconflow_embedding_base_url
        self.default_model = default_model or settings.siliconflow_embedding_model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("SiliconFlow embedding API key not configured")

        payload = {
            "input": texts,
            "model": model or self.default_model,
            "encoding_format": "float",
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                response = await client.post("/embeddings", json=payload)
                response.raise_for_status()
                data = response.json()

                embeddings = []
                for item in data.get("data", []):
                    vec = item.get("embedding", [])
                    embeddings.append(vec)

                if len(embeddings) != len(texts):
                    raise RuntimeError(f"Embedding count mismatch: {len(embeddings)} vs {len(texts)}")

                return embeddings

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)

        raise RuntimeError(f"Embedding failed after {self.max_retries} retries: {redact_string(str(last_error))}")

    async def embed_single(self, text: str, model: str | None = None) -> list[float]:
        results = await self.embed([text], model)
        return results[0] if results else []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class EmbeddingService:
    """Embedding service: manages provider selection and embedding generation."""

    def __init__(self):
        self._provider: EmbeddingProvider | None = None
        self._init_provider()

    def _init_provider(self) -> None:
        key = settings.siliconflow_embedding_api_key
        if key:
            self._provider = SiliconFlowEmbeddingProvider()
        else:
            self._provider = MockEmbeddingProvider()

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        if self._provider is None:
            raise RuntimeError("No embedding provider configured")
        return await self._provider.embed(texts, model)

    async def embed_single(self, text: str, model: str | None = None) -> list[float]:
        results = await self.embed([text], model)
        return results[0] if results else []

    def is_real(self) -> bool:
        return isinstance(self._provider, SiliconFlowEmbeddingProvider)

    async def close(self) -> None:
        if isinstance(self._provider, SiliconFlowEmbeddingProvider):
            await self._provider.close()
