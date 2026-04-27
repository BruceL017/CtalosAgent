"""
Secret Redactor: prevent API keys, tokens, passwords from leaking into logs/events.
"""
import json
import re
from typing import Any


# Patterns that indicate secrets
SECRET_PATTERNS = [
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), '[REDACTED_API_KEY]'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), '[REDACTED_GITHUB_TOKEN]'),
    (re.compile(r'glpat-[a-zA-Z0-9\-]{20}'), '[REDACTED_GITLAB_TOKEN]'),
    (re.compile(r'eyJ[a-zA-Z0-9_/+\-=]{20,}\.eyJ[a-zA-Z0-9_/+\-=]{20,}'), '[REDACTED_JWT]'),
    (re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]+'), 'Bearer [REDACTED]'),
    (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{10,}'), 'api_key=[REDACTED]'),
    (re.compile(r'password["\']?\s*[:=]\s*["\']?[^\s"\']+'), 'password=[REDACTED]'),
    (re.compile(r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-\.]+'), 'token=[REDACTED]'),
    (re.compile(r'secret["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-]+'), 'secret=[REDACTED]'),
]

SENSITIVE_KEYS = {
    "api_key", "apikey", "api-key", "auth_token", "access_token", "refresh_token",
    "password", "secret", "private_key", "authorization", "x-api-key", "token",
    "github_token", "gitlab_token", "lark_app_secret", "supabase_service_key",
    "openai_api_key", "anthropic_api_key", "deepseek_api_key", "siliconflow_api_key",
    "moonshot_api_key", "zhipu_api_key", "google_api_key",
}


def redact_string(value: str) -> str:
    if not isinstance(value, str):
        return value
    result = value
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_value(key: str, value: Any) -> Any:
    if not isinstance(key, str):
        return redact_object(value)
    key_lower = key.lower().replace("-", "_")
    if key_lower in SENSITIVE_KEYS:
        if isinstance(value, str) and len(value) > 0:
            return "[REDACTED]"
        if isinstance(value, (int, float)):
            return "[REDACTED]"
    if isinstance(value, str):
        return redact_string(value)
    return redact_object(value)


def redact_object(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: redact_value(k, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_object(item) for item in obj]
    if isinstance(obj, str):
        return redact_string(obj)
    return obj


def redact_json(text: str) -> str:
    try:
        data = json.loads(text)
        return json.dumps(redact_object(data), ensure_ascii=False)
    except Exception:
        return redact_string(text)
