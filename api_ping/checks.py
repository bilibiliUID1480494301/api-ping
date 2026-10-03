"""Endpoint checks for OpenAI- and Anthropic-compatible APIs (stdlib only).

All check functions return plain dicts with an ``ok`` boolean so they can be
used directly or serialized with :mod:`json`::

    >>> cfg = EndpointConfig(base_url="https://api.openai.com/v1", api_key="sk-...")
    >>> list_models(cfg)        # doctest: +SKIP
    {'ok': True, 'status': 200, 'latency_ms': 212.3, 'count': 42, ...}
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

__all__ = [
    "EndpointConfig",
    "list_models",
    "chat_ping",
    "stream_ping",
    "percentile",
    "run_bench",
]

DEFAULT_TIMEOUT = 15.0
ERROR_SNIPPET = 500


@dataclass
class EndpointConfig:
    """Connection settings. ``base_url`` includes the version segment,
    e.g. ``https://api.openai.com/v1`` or ``https://host/v1``."""

    base_url: str
    api_key: str = ""
    protocol: str = "openai"  # "openai" | "anthropic"
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self):
        self.base_url = self.base_url.rstrip("/")
        if self.protocol not in ("openai", "anthropic"):
            raise ValueError(f"unsupported protocol: {self.protocol!r}")


def _headers(cfg: EndpointConfig) -> dict:
    if cfg.protocol == "anthropic":
        return {
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    return {
        "Authorization": f"Bearer {cfg.api_key}",
        "content-type": "application/json",
    }


def _request(cfg: EndpointConfig, path: str, *, method: str = "GET", body=None):
    """Returns (status, payload_bytes, elapsed_ms, error_or_None)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        cfg.base_url + path, method=method, headers=_headers(cfg), data=data
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            payload = resp.read()
            elapsed = (time.perf_counter() - started) * 1000.0
            return resp.status, payload, elapsed, None
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000.0
        detail = exc.read().decode("utf-8", "replace")[:ERROR_SNIPPET]
        return exc.code, detail, elapsed, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        elapsed = (time.perf_counter() - started) * 1000.0
        return 0, b"", elapsed, str(exc) or exc.__class__.__name__


def _err_result(status: int, elapsed: float, error: str, payload) -> dict:
    if payload:
        error = f"{error}: {payload if isinstance(payload, str) else payload.decode('utf-8', 'replace')}"
    return {"ok": False, "status": status, "latency_ms": round(elapsed, 1), "error": error}


def _chat_body(cfg: EndpointConfig, model: str, max_tokens: int) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
        "max_tokens": max_tokens,
    }


def list_models(cfg: EndpointConfig) -> dict:
    """GET /models -- verifies auth and returns the model list."""
    status, payload, elapsed, error = _request(cfg, "/models")
    if error is not None:
        return {**_err_result(status, elapsed, error, payload), "count": 0, "models": []}
    try:
        data = json.loads(payload.decode("utf-8"))
        ids = [str(m.get("id", "?")) for m in data.get("data", [])]
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return {**_err_result(status, elapsed, "invalid JSON in response", None),
                "count": 0, "models": []}
    return {
        "ok": True,
        "status": status,
        "latency_ms": round(elapsed, 1),
        "count": len(ids),
        "models": ids,
        "error": None,
    }


def chat_ping(cfg: EndpointConfig, model: str, max_tokens: int = 32) -> dict:
    """POST a minimal chat completion and report latency/usage."""
    path = "/messages" if cfg.protocol == "anthropic" else "/chat/completions"
    status, payload, elapsed, error = _request(
        cfg, path, method="POST", body=_chat_body(cfg, model, max_tokens)
    )
    if error is not None:
        return {**_err_result(status, elapsed, error, payload),
                "reply": None, "total_tokens": None}
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {**_err_result(status, elapsed, "invalid JSON in response", None),
                "reply": None, "total_tokens": None}
    if cfg.protocol == "anthropic":
        blocks = data.get("content") or []
        reply = "".join(
            block.get("text", "") for block in blocks if isinstance(block, dict)
        )
        usage = data.get("usage") or {}
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    else:
        choices = data.get("choices") or [{}]
        reply = (choices[0].get("message") or {}).get("content")
        tokens = (data.get("usage") or {}).get("total_tokens")
    return {
        "ok": True,
        "status": status,
        "latency_ms": round(elapsed, 1),
        "reply": reply,
        "total_tokens": tokens,
        "error": None,
    }


def _stream_text(protocol: str, obj: dict) -> str:
    """Extract incremental text from one SSE data payload."""
    if protocol == "anthropic":
        if obj.get("type") == "content_block_delta":
            return (obj.get("delta") or {}).get("text") or ""
        return ""
    choices = obj.get("choices") or [{}]
    delta = choices[0].get("delta") or {}
    return delta.get("content") or ""


def stream_ping(cfg: EndpointConfig, model: str, max_tokens: int = 32) -> dict:
    """POST a streaming chat completion and measure SSE behaviour.

    Reports chunk count, streamed characters, first-token latency and total
    duration -- useful to verify a relay/gateway actually streams.
    """
    path = "/messages" if cfg.protocol == "anthropic" else "/chat/completions"
    body = _chat_body(cfg, model, max_tokens)
    body["stream"] = True
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        cfg.base_url + path, method="POST", headers=_headers(cfg), data=data
    )
    started = time.perf_counter()
    chunks = chars = 0
    first_ms = None
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                if first_ms is None:
                    first_ms = (time.perf_counter() - started) * 1000.0
                chunks += 1
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                chars += len(_stream_text(cfg.protocol, event))
            elapsed = (time.perf_counter() - started) * 1000.0
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000.0
        detail = exc.read().decode("utf-8", "replace")[:ERROR_SNIPPET]
        return {"ok": False, "status": exc.code, "latency_ms": round(elapsed, 1),
                "chunks": 0, "chars": 0, "first_token_ms": None,
                "error": f"HTTP {exc.code}: {detail}"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        elapsed = (time.perf_counter() - started) * 1000.0
        return {"ok": False, "status": 0, "latency_ms": round(elapsed, 1),
                "chunks": 0, "chars": 0, "first_token_ms": None,
                "error": str(exc) or exc.__class__.__name__}
    if chunks == 0:
        return {"ok": False, "status": 200, "latency_ms": round(elapsed, 1),
                "chunks": 0, "chars": 0, "first_token_ms": None,
                "error": "no SSE data received (streaming not supported?)"}
    return {
        "ok": True,
        "status": 200,
        "latency_ms": round(elapsed, 1),
        "chunks": chunks,
        "chars": chars,
        "first_token_ms": round(first_ms, 1) if first_ms is not None else None,
        "error": None,
    }


def percentile(values, pct):
    """Linear-interpolated percentile (pct in 0..100) of a numeric sequence."""
    if not values:
        raise ValueError("percentile of empty sequence")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def run_bench(cfg: EndpointConfig, model: str, n: int = 10, prober=None) -> dict:
    """Run ``n`` sequential chat pings and aggregate latency statistics."""
    n = max(1, int(n))
    prober = prober or chat_ping
    latencies: list = []
    failures = 0
    last_error = None
    for _ in range(n):
        result = prober(cfg, model)
        if result.get("ok"):
            latencies.append(float(result["latency_ms"]))
        else:
            failures += 1
            last_error = result.get("error")
    return {
        "ok": failures == 0,
        "latency_ms": round(percentile(latencies, 50), 1) if latencies else 0.0,
        "requests": n,
        "succeeded": len(latencies),
        "failed": failures,
        "min_ms": round(min(latencies), 1) if latencies else None,
        "mean_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "p50_ms": round(percentile(latencies, 50), 1) if latencies else None,
        "p95_ms": round(percentile(latencies, 95), 1) if latencies else None,
        "max_ms": round(max(latencies), 1) if latencies else None,
        "error": last_error if failures else None,
    }
