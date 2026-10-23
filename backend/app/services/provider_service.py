from __future__ import annotations

import ipaddress
import json
import math
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_key: str = field(repr=False)
    model: str
    base_url: str
    timeout_seconds: float
    max_output_tokens: int
    reasoning_effort: str | None


@dataclass(frozen=True)
class EmbeddingConfig:
    api_key: str = field(repr=False)
    model: str
    base_url: str
    timeout_seconds: float
    dimensions: int


def chat_enabled() -> bool:
    return os.environ.get("CHAT_ENABLED", "false").strip().lower() == "true"


def embeddings_enabled() -> bool:
    return os.environ.get("CHAT_EMBEDDINGS_ENABLED", "true").strip().lower() == "true"


def provider_configured() -> bool:
    if not chat_enabled():
        return False
    try:
        get_provider_config()
        return True
    except ProviderConfigurationError:
        return False


def get_provider_config() -> ProviderConfig:
    provider = os.environ.get("CHAT_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigurationError("OPENAI_API_KEY is required")
        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-5.6-terra").strip()
        model = model or "gpt-5.6-terra"
        base_url = os.environ.get(
            "OPENAI_API_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
    elif provider == "ollama":
        api_key = ""
        model = os.environ.get("OLLAMA_CHAT_MODEL", "").strip()
        if not model:
            raise ProviderConfigurationError("OLLAMA_CHAT_MODEL is required")
        base_url = os.environ.get(
            "OLLAMA_API_BASE_URL", "http://127.0.0.1:11434/v1"
        ).strip().rstrip("/")
        try:
            url = urlsplit(base_url)
            if (
                url.scheme not in {"http", "https"}
                or not ipaddress.ip_address(url.hostname or "").is_loopback
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or (url.port is not None and not 1 <= url.port <= 65535)
                or any(ord(char) < 33 for char in base_url)
            ):
                raise ValueError
        except ValueError as exc:
            raise ProviderConfigurationError(
                "OLLAMA_API_BASE_URL must use HTTP or HTTPS with a loopback IP "
                "and no credentials, query or fragment"
            ) from exc
    else:
        raise ProviderConfigurationError("CHAT_PROVIDER must be openai or ollama")

    reasoning_setting = f"{provider.upper()}_REASONING_EFFORT"
    reasoning_effort = os.environ.get(
        reasoning_setting, "low" if provider == "openai" else ""
    ).strip().lower()
    allowed_efforts = {"none", "low", "medium", "high", "xhigh", "max"}
    if (
        provider == "openai" or reasoning_effort
    ) and reasoning_effort not in allowed_efforts:
        raise ProviderConfigurationError(
            f"{reasoning_setting} must be none, low, medium, high, xhigh, or max"
        )
    try:
        timeout = float(os.environ.get("CHAT_REQUEST_TIMEOUT_SECONDS", "90"))
        output_tokens = int(os.environ.get("CHAT_MAX_OUTPUT_TOKENS", "1200"))
        if not math.isfinite(timeout) or timeout <= 0 or output_tokens <= 0:
            raise ValueError
    except ValueError as exc:
        raise ProviderConfigurationError(
            "CHAT_REQUEST_TIMEOUT_SECONDS and CHAT_MAX_OUTPUT_TOKENS must be positive"
        ) from exc

    return ProviderConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout,
        max_output_tokens=output_tokens,
        reasoning_effort=reasoning_effort or None,
    )


def get_embedding_config() -> EmbeddingConfig:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ProviderConfigurationError("OPENAI_API_KEY is required for embeddings")
    dimensions = int(os.environ.get("OPENAI_EMBEDDING_DIMENSIONS", "256"))
    if dimensions < 64 or dimensions > 3072:
        raise ProviderConfigurationError(
            "OPENAI_EMBEDDING_DIMENSIONS must be between 64 and 3072"
        )
    return EmbeddingConfig(
        api_key=api_key,
        model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large").strip()
        or "text-embedding-3-large",
        base_url=os.environ.get(
            "OPENAI_API_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/"),
        timeout_seconds=float(os.environ.get("CHAT_EMBEDDING_TIMEOUT_SECONDS", "60")),
        dimensions=dimensions,
    )


def _json_data(line: str) -> dict | None:
    if not line.startswith("data:"):
        return None
    raw = line[5:].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_openai_responses_event(line: str) -> list[tuple[str, object]]:
    data = _json_data(line)
    if not data:
        return []
    event_type = data.get("type") or ""
    if event_type == "response.output_text.delta" and data.get("delta"):
        return [("delta", data["delta"])]
    if event_type == "response.completed":
        usage = (data.get("response") or {}).get("usage") or {}
        return [
            (
                "usage",
                {
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or 0),
                },
            )
        ]
    if event_type in {"error", "response.failed", "response.incomplete"}:
        return [("provider_error", "provider_error")]
    return []


def build_openai_request(
    system_prompt: str,
    messages: list[dict[str, object]],
    config: ProviderConfig,
) -> tuple[str, dict[str, str], dict[str, object]]:
    body: dict[str, object] = {
        "model": config.model,
        "instructions": system_prompt,
        "input": messages,
        "stream": True,
        "max_output_tokens": config.max_output_tokens,
    }
    if config.reasoning_effort is not None:
        body["reasoning"] = {"effort": config.reasoning_effort}
    return (
        f"{config.base_url}/responses",
        {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {},
        body,
    )


def build_embeddings_request(
    texts: list[str], config: EmbeddingConfig
) -> tuple[str, dict[str, str], dict[str, object]]:
    return (
        f"{config.base_url}/embeddings",
        {"Authorization": f"Bearer {config.api_key}"},
        {
            "model": config.model,
            "input": texts,
            "dimensions": config.dimensions,
            "encoding_format": "float",
        },
    )


async def create_embeddings(
    texts: list[str],
    config: EmbeddingConfig | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    config = config or get_embedding_config()
    url, headers, body = build_embeddings_request(texts, config)
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(config.timeout_seconds, connect=10)
    )
    try:
        response = await client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            raise ProviderRequestError(f"provider_http_{response.status_code}")
        payload = response.json()
        rows = sorted(payload.get("data") or [], key=lambda item: item.get("index", 0))
        vectors = [row.get("embedding") for row in rows]
        if len(vectors) != len(texts) or any(
            not isinstance(item, list) for item in vectors
        ):
            raise ProviderRequestError("provider_embedding_invalid")
        if any(len(item) != config.dimensions for item in vectors):
            raise ProviderRequestError("provider_embedding_dimension_mismatch")
        return [[float(value) for value in item] for item in vectors]
    except ProviderRequestError:
        raise
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise ProviderRequestError("provider_timeout") from exc
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ProviderRequestError("provider_unavailable") from exc
    finally:
        if owns_client:
            await client.aclose()


async def stream_provider(
    system_prompt: str,
    messages: list[dict[str, object]],
    config: ProviderConfig | None = None,
) -> AsyncIterator[tuple[str, object]]:
    config = config or get_provider_config()
    timeout = httpx.Timeout(config.timeout_seconds, connect=10)

    url, headers, body = build_openai_request(system_prompt, messages, config)

    try:
        async with httpx.AsyncClient(
            timeout=timeout, trust_env=config.provider != "ollama"
        ) as client:
            async with client.stream(
                "POST", url, headers=headers, json=body
            ) as response:
                if response.status_code >= 400:
                    raise ProviderRequestError(f"provider_http_{response.status_code}")
                async for line in response.aiter_lines():
                    for event in parse_openai_responses_event(line):
                        if event[0] == "provider_error":
                            raise ProviderRequestError("provider_stream_error")
                        yield event
                        # Responses usage is emitted only by response.completed.
                        if event[0] == "usage":
                            return
                raise ProviderRequestError("provider_incomplete_response")
    except httpx.TimeoutException as exc:
        raise ProviderRequestError("provider_timeout") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestError("provider_unavailable") from exc
