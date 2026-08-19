from __future__ import annotations

import pytest

from route_agent.observability.redaction import (
    hash_payload,
    payload_fields,
    redact_fields,
    truncate_text,
)


class TestRedaction:
    def test_redacts_nested_secret_keys(self) -> None:
        payload = {
            "api_key": "sk-secret",
            "nested": {"password": "hunter2", "ok": "keep"},
            "items": [{"token": "abc", "name": "x"}],
        }
        redacted = redact_fields(payload)
        assert redacted["api_key"] == "[redacted]"
        assert redacted["nested"]["password"] == "[redacted]"
        assert redacted["nested"]["ok"] == "keep"
        assert redacted["items"][0]["token"] == "[redacted]"
        assert redacted["items"][0]["name"] == "x"

    def test_truncates_long_text(self) -> None:
        text = "a" * 80
        assert truncate_text(text, limit=20) == "a" * 20 + "…(60 more)"

    def test_payload_fields_summarize_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ROUTE_AGENT_TRACE_PAYLOADS", raising=False)
        fields = payload_fields({"prompt": "hello world"}, key="input")
        assert "input" not in fields
        assert fields["input_bytes"] > 0
        assert fields["input_hash"]
        assert "hello" in str(fields["input_preview"])

    def test_payload_fields_include_redacted_body_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_TRACE_PAYLOADS", "true")
        fields = payload_fields({"prompt": "hello", "api_key": "sk"}, key="input")
        assert fields["input"]["prompt"] == "hello"
        assert fields["input"]["api_key"] == "[redacted]"

    def test_hash_is_stable(self) -> None:
        assert hash_payload({"a": 1}) == hash_payload({"a": 1})
