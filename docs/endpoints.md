# Endpoints used by api-ping

`{base}` includes the version segment, e.g. `https://api.openai.com/v1`.

## Paths

| Check | OpenAI shape | Anthropic shape |
|---|---|---|
| `models` | `GET {base}/models` | `GET {base}/models` |
| `chat` | `POST {base}/chat/completions` | `POST {base}/messages` |
| `stream` | `POST {base}/chat/completions` with `"stream": true` | `POST {base}/messages` with `"stream": true` |

## Headers

| Protocol | Auth header | Extra |
|---|---|---|
| `openai` | `Authorization: Bearer <key>` | - |
| `anthropic` | `x-api-key: <key>` | `anthropic-version: 2023-06-01` |

## Environment fallbacks

- `openai` -> `OPENAI_API_KEY`
- `anthropic` -> `ANTHROPIC_API_KEY`

## SSE parsing notes

- Only lines starting with `data:` are treated as events; `event:` lines,
  comments and keep-alives are ignored.
- The OpenAI shape ends with a literal `data: [DONE]` line.
- OpenAI text deltas live at `choices[0].delta.content`; Anthropic text deltas
  arrive as `content_block_delta` events with `delta.text`.
- Zero data events is reported as a failure ("streaming not supported?") --
  this is the typical symptom of a relay that buffers SSE.
