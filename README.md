# api-ping

[![CI](https://github.com/bilibiliUID1480494301/api-ping/actions/workflows/ci.yml/badge.svg)](https://github.com/bilibiliUID1480494301/api-ping/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

> Health-check CLI for OpenAI- and Anthropic-compatible LLM endpoints.
> LLM 接口体检工具：models / chat / stream 三项探测，纯标准库实现。

`api-ping` answers the questions you actually have when a base URL + key "should work":
does auth pass? which models exist? does a chat call return? **does it really stream?**
All with latency numbers, exit codes suitable for CI, and zero dependencies.

## Install

```bash
pip install .            # from a clone
# or just run it in place:
python -m api_ping --help
```

## Usage

```bash
# full check: models + chat + stream
api-ping all --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o-mini

# only verify auth + list models
api-ping models --base-url https://api.openai.com/v1 --api-key sk-...

# streaming probe (first-token latency, chunk/char counts)
api-ping stream --base-url https://relay.example.com/v1 --api-key ... --model gpt-4o-mini --json

# Anthropic-protocol endpoints
api-ping all --protocol anthropic --base-url https://api.anthropic.com/v1 \
    --api-key sk-ant-... --model claude-3-5-haiku-latest
```

API keys can also come from the environment: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`.

### Sample output

```
[ok  ]  models     212.3 ms  --  42 models
[ok  ]  chat       890.1 ms  --  reply='pong', tokens=7
[ok  ]  stream    1204.7 ms  --  chunks=9, chars=4, first-token=310.2 ms
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | all checks passed |
| `1` | at least one check failed |
| `2` | configuration error (missing key / bad protocol) |

## Why

Relay/gateway setups (self-hosted proxies, aggregators, one-click deployments) are
the most common failure point: the endpoint answers `/v1/models` but streaming is
silently buffered, or auth works for one protocol shape but not the other.
`api-ping` is a tiny, dependency-free probe you can run anywhere — including CI.

## Testing

The test suite spins up a local fake upstream speaking both protocol shapes
(including SSE) — no network access needed:

```bash
python -m unittest discover -s tests -t . -v
```

## Roadmap

See the [open issues](../../issues) — `bench` subcommand with p50/p95, embeddings
probe, multi-endpoint comparison.

## License

[MIT](LICENSE)

---

> **AI-assisted development statement / AI 辅助开发声明**: this project was written
> with the help of an AI coding agent and is published as a real, working tool —
> every feature is covered by the unit tests in [`tests/`](tests/).
