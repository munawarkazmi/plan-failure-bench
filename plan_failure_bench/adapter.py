"""Model adapters: one interface, two wire formats.

Backends:
- "openai_chat": POST {base_url}/chat/completions with an OpenAI style
  payload. Covers local servers (llama.cpp, Ollama) and any OpenAI
  compatible API. Local versus remote is purely a base_url difference.
- "anthropic": POST {base_url}/messages with Anthropic headers and payload.
  The Anthropic API is not OpenAI compatible, and current Anthropic models
  reject the temperature parameter, so pretending one wire format covers
  both would fail at runtime. Temperature is never sent on this backend.

Everything is stdlib urllib. API keys come from environment variables named
in the config and are never written to disk or results.
"""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .schema import SchemaError

BACKENDS = ("openai_chat", "anthropic")
_RETRYABLE_STATUS = (408, 429, 500, 502, 503, 529)
_MAX_ATTEMPTS = 5


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelConfig:
    name: str
    backend: str
    base_url: str
    model: str
    api_key_env: str | None = None
    temperature: float | None = 0.0
    max_tokens: int = 2000
    timeout_s: float = 180.0


@dataclass(frozen=True)
class ModelResponse:
    text: str
    attempts: int
    latency_s: float


_CONFIG_KEYS = {"name", "backend", "base_url", "model", "api_key_env", "temperature", "max_tokens", "timeout_s"}


def load_model_configs(path: str | Path) -> dict[str, ModelConfig]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SchemaError(f"{path}: expected a list of model configs")
    configs: dict[str, ModelConfig] = {}
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SchemaError(f"models[{i}]: expected an object")
        unknown = sorted(entry.keys() - _CONFIG_KEYS)
        missing = sorted({"name", "backend", "base_url", "model"} - entry.keys())
        if unknown or missing:
            raise SchemaError(f"models[{i}]: missing keys {missing}, unknown keys {unknown}")
        if entry["backend"] not in BACKENDS:
            raise SchemaError(f"models[{i}]: backend must be one of {BACKENDS}, got {entry['backend']!r}")
        config = ModelConfig(**entry)
        if config.name in configs:
            raise SchemaError(f"duplicate model config name {config.name!r}")
        configs[config.name] = config
    return configs


def _api_key(config: ModelConfig) -> str | None:
    if config.api_key_env is None:
        return None
    key = os.environ.get(config.api_key_env)
    if not key:
        raise AdapterError(f"model {config.name!r} needs the environment variable {config.api_key_env} to be set")
    return key


def _request(config: ModelConfig) -> tuple[str, dict, dict]:
    base = config.base_url.rstrip("/")
    key = _api_key(config)
    # Some API gateways block the default Python-urllib user agent outright
    # (Cloudflare bot filtering returns 403 Forbidden), so identify honestly.
    common = {"Content-Type": "application/json", "User-Agent": "plan-failure-bench/0.0.1"}
    if config.backend == "openai_chat":
        url = f"{base}/chat/completions"
        payload = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [],
        }
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        headers = dict(common)
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        return url, payload, headers
    if config.backend == "anthropic":
        url = f"{base}/messages"
        payload = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [],
        }
        headers = dict(common)
        headers["anthropic-version"] = "2023-06-01"
        if key is not None:
            headers["x-api-key"] = key
        return url, payload, headers
    raise AssertionError(f"unhandled backend {config.backend!r}")


def _extract_text(config: ModelConfig, data: dict) -> str:
    if config.backend == "openai_chat":
        return data["choices"][0]["message"]["content"]
    return "".join(block["text"] for block in data.get("content", []) if block.get("type") == "text")


def _http_transport(url: str, payload: dict, headers: dict, timeout_s: float) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    """Backoff that respects the server's Retry-After when it sends one.

    Rate limits (429) on free tiers refill by the minute, so short
    exponential backoff alone gives up before the window resets.
    """
    delay = float(2**attempt)
    header = exc.headers.get("Retry-After") if exc.headers is not None else None
    if header is not None:
        try:
            delay = max(delay, float(header) + 1.0)
        except ValueError:
            pass
    if exc.code == 429:
        delay = max(delay, 15.0)
    return min(delay, 120.0)


def call_model(config: ModelConfig, prompt: str, transport=None) -> ModelResponse:
    transport = transport or _http_transport
    url, payload, headers = _request(config)
    payload["messages"] = [{"role": "user", "content": prompt}]
    start = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            data = transport(url, payload, headers, config.timeout_s)
            return ModelResponse(
                text=_extract_text(config, data),
                attempts=attempt,
                latency_s=time.monotonic() - start,
            )
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in _RETRYABLE_STATUS:
                # Error bodies usually say exactly what the server objected
                # to; losing them turns a one-line fix into archaeology.
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:400]
                except Exception:
                    body = ""
                raise AdapterError(
                    f"model {config.name!r}: HTTP {exc.code} {exc.reason}: {body}"
                ) from exc
            delay = _retry_delay(exc, attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
            # Dropped connections and read timeouts surface as raw socket or
            # http.client errors, not URLError; all are transient here.
            last_error = exc
            delay = float(2**attempt)
        if attempt < _MAX_ATTEMPTS:
            time.sleep(delay)
    raise AdapterError(f"model {config.name!r}: request failed after {_MAX_ATTEMPTS} attempts") from last_error
