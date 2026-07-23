"""Tests for the model adapters, using an injected transport. No network."""

import json
from pathlib import Path

import pytest

from plan_failure_bench.adapter import AdapterError, ModelConfig, call_model, load_model_configs
from plan_failure_bench.schema import SchemaError

REPO_ROOT = Path(__file__).resolve().parent.parent

OPENAI_CONFIG = ModelConfig(
    name="local", backend="openai_chat", base_url="http://localhost:8080/v1", model="qwen"
)
ANTHROPIC_CONFIG = ModelConfig(
    name="anthropic_api",
    backend="anthropic",
    base_url="https://api.anthropic.com/v1",
    model="example-model-id",
    api_key_env="FAKE_ANTHROPIC_KEY",
    temperature=None,
)


class CapturingTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, payload, headers, timeout_s):
        self.calls.append((url, payload, headers, timeout_s))
        return self.response


class TestOpenAiBackend:
    def test_request_and_extraction(self):
        transport = CapturingTransport({"choices": [{"message": {"content": '{"plan": []}'}}]})
        result = call_model(OPENAI_CONFIG, "the prompt", transport=transport)
        assert result.text == '{"plan": []}'
        assert result.attempts == 1
        url, payload, headers, _ = transport.calls[0]
        assert url == "http://localhost:8080/v1/chat/completions"
        assert payload["messages"] == [{"role": "user", "content": "the prompt"}]
        assert payload["temperature"] == 0.0
        assert "Authorization" not in headers


class TestAnthropicBackend:
    def test_request_and_extraction(self, monkeypatch):
        monkeypatch.setenv("FAKE_ANTHROPIC_KEY", "sk-test")
        transport = CapturingTransport(
            {"content": [{"type": "text", "text": '{"infeasible": {"reason": "unreachable"}}'}]}
        )
        result = call_model(ANTHROPIC_CONFIG, "the prompt", transport=transport)
        assert result.text == '{"infeasible": {"reason": "unreachable"}}'
        url, payload, headers, _ = transport.calls[0]
        assert url == "https://api.anthropic.com/v1/messages"
        assert headers["x-api-key"] == "sk-test"
        assert headers["anthropic-version"] == "2023-06-01"
        # Current Anthropic models reject temperature; it must never be sent.
        assert "temperature" not in payload

    def test_missing_key_is_a_clear_error(self, monkeypatch):
        monkeypatch.delenv("FAKE_ANTHROPIC_KEY", raising=False)
        with pytest.raises(AdapterError, match="FAKE_ANTHROPIC_KEY"):
            call_model(ANTHROPIC_CONFIG, "x", transport=lambda *a: {})

    def test_non_text_blocks_ignored(self, monkeypatch):
        monkeypatch.setenv("FAKE_ANTHROPIC_KEY", "sk-test")
        transport = CapturingTransport(
            {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": "ok"}]}
        )
        assert call_model(ANTHROPIC_CONFIG, "x", transport=transport).text == "ok"


class TestConfigLoading:
    def test_example_config_loads(self):
        configs = load_model_configs(REPO_ROOT / "configs" / "models.example.json")
        assert set(configs) == {"local_qwen", "anthropic_api"}
        assert configs["anthropic_api"].backend == "anthropic"
        assert configs["anthropic_api"].temperature is None

    def test_bad_backend_rejected(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text(json.dumps([{"name": "x", "backend": "grpc", "base_url": "u", "model": "m"}]))
        with pytest.raises(SchemaError, match="backend"):
            load_model_configs(p)

    def test_unknown_key_rejected(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text(
            json.dumps([{"name": "x", "backend": "openai_chat", "base_url": "u", "model": "m", "seed": 1}])
        )
        with pytest.raises(SchemaError, match="unknown keys"):
            load_model_configs(p)
