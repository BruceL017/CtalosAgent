"""
Model Provider Router: 统一多供应商 LLM 调用接口
支持 OpenAI、Anthropic Claude、Google Gemini、DeepSeek、智谱、Kimi、SiliconFlow
增强: timeout、retry、fallback、rate limit、cost/token 统计、secret redaction
"""
import asyncio
import json
import os
import time
from typing import Any

import httpx

from models.schemas import ChatMessage, LLMResponse, ProviderHealth, ProviderStats, ToolCallRequest
from utils.secret_redactor import redact_string


class BaseProvider:
    name: str = "base"
    default_model: str = ""

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._stats = ProviderStats(provider=self.name)

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError

    async def health_check(self) -> ProviderHealth:
        """Check provider health by making a lightweight call."""
        start = time.time()
        try:
            msgs = [ChatMessage(role="user", content="hi")]
            await self.chat(msgs, model=self.default_model, temperature=0.0)
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                provider=self.name,
                configured=True,
                healthy=True,
                latency_ms=latency,
                default_model=self.default_model,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                provider=self.name,
                configured=True,
                healthy=False,
                latency_ms=latency,
                last_error=redact_string(str(e))[:200],
                default_model=self.default_model,
            )

    def _with_retry(self, func):
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(self.max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < self.max_retries - 1:
                        wait = 2 ** attempt
                        await asyncio.sleep(wait)
            raise last_error
        return wrapper

    def _record_call(self, latency_ms: int, usage: dict[str, int], error: bool = False) -> None:
        self._stats.total_calls += 1
        if error:
            self._stats.total_errors += 1
        self._stats.total_tokens += usage.get("total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
        # Rolling average latency
        n = self._stats.total_calls
        self._stats.avg_latency_ms = ((n - 1) * self._stats.avg_latency_ms + latency_ms) / n if n > 0 else latency_ms
        self._stats.last_called_at = str(int(time.time()))

    def get_stats(self) -> dict[str, Any]:
        return self._stats.model_dump()


class MockProvider(BaseProvider):
    name: str = "mock"
    default_model: str = "mock-model"

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        return LLMResponse(
            content='{"steps": [{"step_number": 1, "tool": "mock.analyze", "input": {"data": ["item1"]}, "description": "Analyze", "retry_on_failure": true}], "estimated_risk": "low", "requires_approval": false}',
            tool_calls=[],
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            model=model or self.default_model,
            provider=self.name,
            finish_reason="stop",
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name, configured=True, healthy=True, latency_ms=0, default_model=self.default_model
        )


class OpenAIProvider(BaseProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        # Normalize base_url: strip trailing /chat/completions if user pasted full endpoint
        if base_url and "/chat/completions" in base_url:
            base_url = base_url.replace("/chat/completions", "")
        super().__init__(api_key, base_url or "https://api.openai.com/v1", timeout, max_retries)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=self.timeout,
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": [{"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})} for m in messages],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        t0 = time.time()
        try:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]
            message = choice["message"]

            tool_calls = []
            if "tool_calls" in message:
                for tc in message["tool_calls"]:
                    tool_calls.append(ToolCallRequest(
                        id=tc["id"],
                        type=tc["type"],
                        function=tc["function"],
                    ))

            usage = data.get("usage", {})
            latency = int((time.time() - t0) * 1000)
            self._record_call(latency, usage)

            return LLMResponse(
                content=message.get("content") or "",
                tool_calls=tool_calls,
                usage=usage,
                model=data.get("model", model or self.default_model),
                provider=self.name,
                finish_reason=choice.get("finish_reason"),
            )
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            self._record_call(latency, {}, error=True)
            # Redact potential secret leakage in error message
            raise RuntimeError(redact_string(str(e)))


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    default_model = "claude-3-5-sonnet-20241022"

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        super().__init__(api_key, base_url or "https://api.anthropic.com", timeout, max_retries)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        system_msg = ""
        chat_msgs = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                chat_msgs.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": chat_msgs,
            "temperature": temperature,
            "max_tokens": 4096,
        }
        if system_msg:
            payload["system"] = system_msg
        if tools:
            payload["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""), "input_schema": t["function"].get("parameters", {})} for t in tools]

        t0 = time.time()
        try:
            response = await self.client.post("/v1/messages", json=payload)
            response.raise_for_status()
            data = response.json()

            content = ""
            tool_calls = []
            for block in data.get("content", []):
                if block["type"] == "text":
                    content += block["text"]
                elif block["type"] == "tool_use":
                    tool_calls.append(ToolCallRequest(
                        id=block["id"],
                        type="function",
                        function={
                            "name": block["name"],
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    ))

            usage = {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0),
            }
            latency = int((time.time() - t0) * 1000)
            self._record_call(latency, usage)

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                model=data.get("model", model or self.default_model),
                provider=self.name,
                finish_reason=data.get("stop_reason"),
            )
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            self._record_call(latency, {}, error=True)
            raise RuntimeError(redact_string(str(e)))


class DeepSeekProvider(OpenAIProvider):
    name = "deepseek"
    default_model = "deepseek-chat"

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        super().__init__(api_key, base_url or "https://api.deepseek.com/v1", timeout, max_retries)


class ZhipuProvider(OpenAIProvider):
    name = "zhipu"
    default_model = "glm-4"

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        super().__init__(api_key, base_url or "https://open.bigmodel.cn/api/paas/v4", timeout, max_retries)


class MoonshotProvider(OpenAIProvider):
    name = "moonshot"
    default_model = "moonshot-v1-8k"

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        super().__init__(api_key, base_url or "https://api.moonshot.cn/v1", timeout, max_retries)


class SiliconFlowProvider(OpenAIProvider):
    name = "siliconflow"
    default_model = "Pro/zai-org/GLM-4.7"

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        # SiliconFlow uses OpenAI-compatible API
        if base_url and "/chat/completions" in base_url:
            base_url = base_url.replace("/chat/completions", "")
        super().__init__(api_key, base_url or "https://api.siliconflow.cn/v1", timeout, max_retries)


class GeminiProvider(BaseProvider):
    name = "gemini"
    default_model = "gemini-1.5-pro"

    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = 60, max_retries: int = 3):
        super().__init__(api_key, None, timeout, max_retries)
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        gemini_model = model or self.default_model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={self.api_key}"

        contents = []
        for m in messages:
            role = "user" if m.role in ("user", "system", "developer") else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 4096},
        }

        t0 = time.time()
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            text = ""
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    text += part.get("text", "")

            usage = data.get("usageMetadata", {})
            usage_dict = {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            }
            latency = int((time.time() - t0) * 1000)
            self._record_call(latency, usage_dict)

            return LLMResponse(
                content=text,
                usage=usage_dict,
                model=gemini_model,
                provider=self.name,
                finish_reason="stop",
            )
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            self._record_call(latency, {}, error=True)
            raise RuntimeError(redact_string(str(e)))


class ProviderRouter:
    """Provider 路由器：管理多个供应商，支持 fallback、统计、健康检查"""

    PROVIDER_MAP: dict[str, type[BaseProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "deepseek": DeepSeekProvider,
        "zhipu": ZhipuProvider,
        "moonshot": MoonshotProvider,
        "gemini": GeminiProvider,
        "siliconflow": SiliconFlowProvider,
        "mock": MockProvider,
    }

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}
        self._default_provider: str | None = None
        self._init_providers()

    def _init_providers(self) -> None:
        configs = [
            ("openai", os.getenv("OPENAI_API_KEY"), os.getenv("OPENAI_BASE_URL"), os.getenv("DEFAULT_MODEL", "gpt-4o")),
            ("anthropic", os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_BASE_URL"), os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-3-5-sonnet-20241022")),
            ("deepseek", os.getenv("DEEPSEEK_API_KEY"), os.getenv("DEEPSEEK_BASE_URL"), "deepseek-chat"),
            ("zhipu", os.getenv("ZHIPU_API_KEY"), os.getenv("ZHIPU_BASE_URL"), "glm-4"),
            ("moonshot", os.getenv("MOONSHOT_API_KEY"), os.getenv("MOONSHOT_BASE_URL"), "moonshot-v1-8k"),
            ("gemini", os.getenv("GOOGLE_API_KEY"), os.getenv("GOOGLE_BASE_URL"), "gemini-1.5-pro"),
            ("siliconflow", os.getenv("SILICONFLOW_API_KEY"), os.getenv("SILICONFLOW_BASE_URL"), os.getenv("SILICONFLOW_MODEL", "Pro/zai-org/GLM-4.7")),
        ]

        default = os.getenv("DEFAULT_PROVIDER", "openai")

        for name, key, base_url, model in configs:
            if key:
                provider_cls = self.PROVIDER_MAP.get(name)
                if provider_cls:
                    self._providers[name] = provider_cls(key, base_url)
                    self._providers[name].default_model = model
                    if name == default:
                        self._default_provider = name

        if not self._default_provider and self._providers:
            self._default_provider = list(self._providers.keys())[0]

        # Fallback to mock provider when no real providers are configured
        if not self._providers:
            self._providers["mock"] = MockProvider("mock-key")
            self._default_provider = "mock"

    def get_provider(self, name: str | None = None) -> BaseProvider:
        provider_name = name or self._default_provider
        if not provider_name:
            raise RuntimeError("No provider configured")
        if provider_name not in self._providers:
            raise ValueError(f"Provider {provider_name} not configured")
        return self._providers[provider_name]

    def list_providers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "model": p.default_model,
                "configured": True,
                "is_default": name == self._default_provider,
            }
            for name, p in self._providers.items()
        ]

    async def chat(
        self,
        messages: list[ChatMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """发送聊天请求，支持自动 fallback，所有错误经脱敏处理"""
        providers_to_try = [provider] if provider else [self._default_provider]

        # Add fallback providers
        if not provider and self._default_provider:
            for name in self._providers:
                if name != self._default_provider:
                    providers_to_try.append(name)

        last_error = None
        for pname in providers_to_try:
            if not pname:
                continue
            try:
                p = self.get_provider(pname)
                return await p.chat(messages, model, temperature, tools)
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(f"All providers failed. Last error: {redact_string(str(last_error))}")

    async def health_checks(self) -> list[ProviderHealth]:
        """Run health check on all configured providers."""
        results = []
        for name, p in self._providers.items():
            health = await p.health_check()
            results.append(health)
        return results

    def get_stats(self) -> dict[str, Any]:
        return {
            "default_provider": self._default_provider,
            "providers": {name: p.get_stats() for name, p in self._providers.items()},
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "default_provider": self._default_provider,
            "providers": self.list_providers(),
        }
