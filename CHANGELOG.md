# Changelog

All notable changes to this project are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
### Planned
- `bench` subcommand with p50/p95 latency report

## [0.1.0] - 2026-10-03
### Added
- `models` / `chat` / `stream` / `all` subcommands
- OpenAI and Anthropic wire-protocol support
- SSE streaming probe: chunk count, streamed chars, first-token latency
- `--json` machine-readable output; exit codes 0 / 1 / 2
- Environment fallback for keys (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`)
- Fake-upstream test suite (incl. SSE) and CI on Python 3.9-3.13
