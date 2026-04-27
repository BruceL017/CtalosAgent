"""Tests for secret redaction across events, tool calls, and provider errors."""
import pytest

from utils.secret_redactor import redact_object, redact_string


class TestSecretRedaction:
    def test_redact_api_key(self):
        text = "Authorization: Bearer sk-zdcqxyzippchhnvitxrecyxsatghdtagdpacutulyghzcuzj"
        result = redact_string(text)
        assert "sk-" not in result
        assert "[REDACTED" in result

    def test_redact_github_token(self):
        text = "token ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_string(text)
        assert "ghp_" not in result
        assert "[REDACTED" in result

    def test_redact_jwt(self):
        text = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = redact_string(text)
        assert "eyJhbG" not in result
        assert "[REDACTED" in result

    def test_redact_object_dict(self):
        data = {
            "api_key": "sk-secret123456789",
            "password": "my_password_123",
            "token": "abc.def.ghi",
            "normal_field": "this is fine",
        }
        result = redact_object(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["password"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"
        assert result["normal_field"] == "this is fine"

    def test_redact_nested_object(self):
        data = {
            "config": {
                "openai_api_key": "sk-abc123",
                "nested": {
                    "secret": "shh",
                },
            },
            "items": [
                {"token": "item_token_1"},
                "Bearer sk-xyz",
            ],
        }
        result = redact_object(data)
        assert result["config"]["openai_api_key"] == "[REDACTED]"
        assert result["config"]["nested"]["secret"] == "[REDACTED]"
        assert result["items"][0]["token"] == "[REDACTED]"
        assert "[REDACTED" in result["items"][1]

    def test_no_false_positives_on_short_strings(self):
        text = "ski resort is nice"
        result = redact_string(text)
        # "ski" is not a secret pattern
        assert "ski resort" in result

    def test_provider_error_redaction(self):
        """Simulate an error that might contain API key in traceback."""
        raw_error = "HTTP 401: Invalid API key sk-zdcqxyzippchhnvitxrecyxsatghdtagdpacutulyghzcuzj"
        redacted = redact_string(raw_error)
        assert "sk-zdcq" not in redacted
        assert "[REDACTED_API_KEY]" in redacted
