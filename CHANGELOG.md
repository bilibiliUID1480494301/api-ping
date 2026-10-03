# Changelog

All notable changes to this project are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
### Planned
- Embeddings endpoint probe (`/v1/embeddings`)
- Multi-endpoint comparison in a single run
- HTML report output

## [0.2.0] - 2026-10-03
### Added
- `bench` subcommand: runs N sequential chat pings and reports
  min / mean / p50 / p95 / max latency plus the success count
  (`-n`/`--count`, default 10); linear-interpolated `percentile()` helper

## [0.1.0] - 2026-10-03
### Added
- `models` / `chat` / `stream` / `all` subcommands
- OpenAI and Anthropic wire-protocol support
- SSE streaming probe: chunk count, streamed chars, first-token latency
- `--json` machine-readable output; exit codes 0 / 1 / 2
- Environment fallback for keys (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`)
- Fake-upstream test suite (incl. SSE) and CI on Python 3.9-3.13
