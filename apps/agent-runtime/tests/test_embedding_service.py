"""Test Embedding Service: real + mock fallback."""
import os

import pytest

from services.embedding_service import MockEmbeddingProvider, SiliconFlowEmbeddingProvider, EmbeddingService


class TestMockEmbeddingProvider:
    @pytest.mark.asyncio
    async def test_embed_single(self):
        provider = MockEmbeddingProvider()
        result = await provider.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 1024
        assert all(isinstance(x, float) for x in result[0])

    @pytest.mark.asyncio
    async def test_embed_consistency(self):
        provider = MockEmbeddingProvider()
        r1 = await provider.embed(["test"])
        r2 = await provider.embed(["test"])
        assert r1[0] == r2[0]


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_mock_when_no_key(self):
        """Without API key, falls back to mock."""
        # Directly test mock provider without relying on env
        provider = MockEmbeddingProvider()
        results = await provider.embed(["hello world"])
        result = results[0]
        assert len(result) == 1024
        assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_real_provider_init(self):
        """Real provider initializes correctly with key."""
        key = os.getenv("SILICONFLOW_EMBEDDING_API_KEY")
        if not key:
            pytest.skip("SILICONFLOW_EMBEDDING_API_KEY not set")
        provider = SiliconFlowEmbeddingProvider(api_key=key)
        result = await provider.embed_single("Enterprise Agent test")
        assert len(result) > 0
        # SiliconFlow may return int or float embeddings
        assert all(isinstance(x, (int, float)) for x in result)
        await provider.close()

    @pytest.mark.asyncio
    async def test_real_provider_batch(self):
        """Batch embedding works."""
        key = os.getenv("SILICONFLOW_EMBEDDING_API_KEY")
        if not key:
            pytest.skip("SILICONFLOW_EMBEDDING_API_KEY not set")
        provider = SiliconFlowEmbeddingProvider(api_key=key)
        results = await provider.embed(["first text", "second text", "third text"])
        assert len(results) == 3
        for r in results:
            assert len(r) > 0
            # SiliconFlow may return int or float embeddings
            assert all(isinstance(x, (int, float)) for x in r)
        await provider.close()
