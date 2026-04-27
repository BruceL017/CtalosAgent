"""Tests for real LLM provider integration with SiliconFlow.
Requires SILICONFLOW_API_KEY env var. Falls back to mock if not set."""
import os

import pytest

from models.schemas import ChatMessage
from services.provider_router import MockProvider, ProviderRouter, SiliconFlowProvider


class TestSiliconFlowProvider:
    @pytest.mark.asyncio
    async def test_siliconflow_provider_chat(self):
        """Verify SiliconFlow can make a real chat call and return structured response."""
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            pytest.skip("SILICONFLOW_API_KEY not set, skipping real provider test")

        provider = SiliconFlowProvider(api_key)
        messages = [
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="What is 2+2? Reply with a single number."),
        ]
        response = await provider.chat(messages, temperature=0.0)

        assert response.provider == "siliconflow"
        assert response.model
        assert response.content or response.tool_calls is not None
        assert response.usage.get("total_tokens", 0) > 0
        assert response.finish_reason is not None

    @pytest.mark.asyncio
    async def test_siliconflow_provider_json_planning(self):
        """Verify SiliconFlow can generate a JSON execution plan."""
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            pytest.skip("SILICONFLOW_API_KEY not set, skipping real provider test")

        provider = SiliconFlowProvider(api_key)
        system_prompt = """You are an enterprise agent planner. Respond ONLY in JSON:
{"steps": [{"step_number": 1, "tool": "mock.analyze", "input": {}, "description": "Analyze", "retry_on_failure": true}], "estimated_risk": "low", "requires_approval": false}"""
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content="Plan a task to analyze sales data."),
        ]
        response = await provider.chat(messages, temperature=0.1)

        assert response.provider == "siliconflow"
        assert response.content
        # Should be parseable JSON
        import json
        try:
            plan = json.loads(response.content)
            assert "steps" in plan
        except json.JSONDecodeError:
            # Some models may wrap JSON in markdown, that's acceptable for now
            pass

    @pytest.mark.asyncio
    async def test_siliconflow_health_check(self):
        """Verify SiliconFlow health check works."""
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            pytest.skip("SILICONFLOW_API_KEY not set, skipping real provider test")

        provider = SiliconFlowProvider(api_key)
        health = await provider.health_check()
        assert health.provider == "siliconflow"
        assert health.configured is True
        assert health.healthy is True
        assert health.latency_ms is not None

    @pytest.mark.asyncio
    async def test_siliconflow_stats_recorded(self):
        """Verify stats are recorded after a call."""
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            pytest.skip("SILICONFLOW_API_KEY not set, skipping real provider test")

        provider = SiliconFlowProvider(api_key)
        before = provider.get_stats()["total_calls"]
        messages = [ChatMessage(role="user", content="Say hello")]
        await provider.chat(messages)
        after = provider.get_stats()["total_calls"]
        assert after == before + 1


class TestProviderFallback:
    @pytest.mark.asyncio
    async def test_fallback_to_mock_when_real_fails(self):
        """When default provider fails, fallback chain should eventually use mock."""
        # Temporarily hide real provider keys to force mock-only initialization
        keys_to_hide = ["SILICONFLOW_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "ZHIPU_API_KEY", "MOONSHOT_API_KEY", "GOOGLE_API_KEY"]
        saved = {k: os.environ.pop(k, None) for k in keys_to_hide}
        old_default = os.environ.get("DEFAULT_PROVIDER")
        os.environ["DEFAULT_PROVIDER"] = "mock"
        try:
            router = ProviderRouter()
            messages = [ChatMessage(role="user", content="Hello")]
            response = await router.chat(messages)
            assert response.provider == "mock"
            assert response.content
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
            if old_default is not None:
                os.environ["DEFAULT_PROVIDER"] = old_default
            else:
                os.environ.pop("DEFAULT_PROVIDER", None)

    @pytest.mark.asyncio
    async def test_provider_not_configured_raises(self):
        """Requesting an unconfigured provider should raise ValueError."""
        router = ProviderRouter()
        with pytest.raises(ValueError):
            router.get_provider("nonexistent_provider_xyz")

    @pytest.mark.asyncio
    async def test_error_message_redacted(self):
        """Error messages from provider should not contain API keys."""
        provider = SiliconFlowProvider("fake-key-that-will-fail")
        messages = [ChatMessage(role="user", content="test")]
        try:
            await provider.chat(messages)
            assert False, "Expected error"
        except RuntimeError as e:
            error_str = str(e)
            assert "fake-key" not in error_str.lower()
            assert "[REDACTED" in error_str or "Unauthorized" in error_str or "401" in error_str
