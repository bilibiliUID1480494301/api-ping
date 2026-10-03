"""Command-line interface for api-ping."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .checks import EndpointConfig, chat_ping, list_models, stream_ping

ENV_KEYS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="api-ping",
        description="Health-check CLI for OpenAI/Anthropic-compatible LLM endpoints.",
    )
    parser.add_argument("--version", action="version", version=f"api-ping {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--base-url", required=True,
        help="API base URL including the version segment, e.g. https://api.openai.com/v1",
    )
    common.add_argument(
        "--api-key", default="",
        help="API key (falls back to $OPENAI_API_KEY / $ANTHROPIC_API_KEY)",
    )
    common.add_argument(
        "--protocol", choices=("openai", "anthropic"), default="openai",
        help="wire protocol of the endpoint (default: openai)",
    )
    common.add_argument("--timeout", type=float, default=15.0, help="seconds (default: 15)")
    common.add_argument("--json", action="store_true", help="emit JSON instead of text")

    sub.add_parser("models", parents=[common], help="list models / verify auth")
    p_chat = sub.add_parser("chat", parents=[common], help="send a minimal chat completion")
    p_stream = sub.add_parser("stream", parents=[common], help="test SSE streaming")
    p_all = sub.add_parser("all", parents=[common], help="run models + chat + stream")
    for p in (p_chat, p_stream, p_all):
        p.add_argument("--model", required=True, help="model name to probe with")
    return parser


def _cfg(args: argparse.Namespace) -> EndpointConfig:
    key = args.api_key or os.environ.get(ENV_KEYS[args.protocol], "")
    if not key:
        print(
            f"api-ping: no API key given (use --api-key or ${ENV_KEYS[args.protocol]})",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        return EndpointConfig(
            base_url=args.base_url, api_key=key, protocol=args.protocol, timeout=args.timeout
        )
    except ValueError as exc:
        print(f"api-ping: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _run(cfg: EndpointConfig, args: argparse.Namespace) -> dict:
    if args.command == "models":
        return {"models": list_models(cfg)}
    if args.command == "chat":
        return {"chat": chat_ping(cfg, args.model)}
    if args.command == "stream":
        return {"stream": stream_ping(cfg, args.model)}
    return {
        "models": list_models(cfg),
        "chat": chat_ping(cfg, args.model),
        "stream": stream_ping(cfg, args.model),
    }


def _describe(name: str, result: dict) -> str:
    if name == "models":
        return f"{result['count']} models"
    if name == "chat":
        text = f"reply={result['reply']!r}"
        if result.get("total_tokens") is not None:
            text += f", tokens={result['total_tokens']}"
        return text
    if name == "stream":
        text = f"chunks={result['chunks']}, chars={result['chars']}"
        if result.get("first_token_ms") is not None:
            text += f", first-token={result['first_token_ms']:.1f} ms"
        return text
    return ""


def _print_result(name: str, result: dict) -> None:
    mark = "ok  " if result["ok"] else "FAIL"
    head = f"[{mark}] {name:<7} {result.get('latency_ms', 0):>9.1f} ms"
    if result["ok"]:
        print(f"{head}  --  {_describe(name, result)}")
    else:
        print(f"{head}  --  {result.get('error') or 'unknown error'}")


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = _cfg(args)
    results = _run(cfg, args)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for name, result in results.items():
            _print_result(name, result)
    return 0 if all(r["ok"] for r in results.values()) else 1
