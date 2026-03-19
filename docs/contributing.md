# Contributing to piai

## Setup

```bash
git clone https://github.com/Xplo8E/piai
cd piai
uv sync
```

## Running tests

```bash
# Use the local venv's python directly (avoids workspace venv conflicts)
.venv/bin/python -m pytest tests/ -v

# Quick pass/fail
.venv/bin/python -m pytest tests/ -q
```

All 203 tests should pass. If you add new functionality, add tests for it.

## Project structure

```
piai/
├── src/piai/         # Library source
├── tests/            # Pytest test suite (203 tests across 7 files)
├── docs/             # Documentation
│   ├── architecture.md   # High-level design and flow
│   ├── internals.md      # Per-module deep-dive
│   ├── mcp.md            # Full MCP usage reference
│   ├── contributing.md   # This file
│   └── AGENTS.md         # AI agent context (auto-updated on changes)
├── pyproject.toml    # Package config, deps, scripts
└── README.md         # User-facing docs
```

## Making changes

Before touching any module, read the corresponding section in `docs/internals.md`. Each module has specific invariants (especially around auth.json format, JWT decoding, and the stream processor state machine) that must be preserved.

Key rules:
- **auth.json keys must stay camelCase** (`accountId`, not `account_id`) — JS SDK compatibility
- **`expires` is Unix milliseconds**, not seconds
- **Stream processor order matters** — SSE events must be handled in the exact sequence the Responses API sends them. Check `internals.md` before modifying `_StreamProcessor`.
- **No retry on usage limit errors** — `"usage limit"` in the error message means the plan is exhausted; retrying just wastes time.
- **Tool call IDs must be ≤ 64 chars** — use `_make_tc_id(call_id, item_id)` from `providers/openai_codex.py`.
- **Do not mutate the caller's `options` dict** — always copy before modifying in `stream.py`.
- **SSE line endings** — normalize CRLF/CR to LF in `_parse_sse` before splitting.

## Test files

| File | What it tests |
|------|--------------|
| `test_pkce.py` | PKCE verifier/challenge generation |
| `test_oauth_codex.py` | JWT decoding, auth URL construction, credential serialization |
| `test_message_transform.py` | Context → Responses API conversion, `_clamp_reasoning_effort`, `_make_tc_id` |
| `test_stream_processor.py` | `_StreamProcessor` state machine (text, tool calls, thinking, errors, edge cases) |
| `test_sse_parser.py` | SSE parsing (CRLF normalization, split chunks, multi-event, invalid JSON) |
| `test_mcp.py` | MCPServer config, MCPClient, MCPHub, agent loop |
| `test_langchain.py` | PiAIChatModel, message conversion, streaming, bind_tools |

New tests should use plain pytest and `AsyncMock`/`MagicMock` to avoid real network calls. The `asyncio_mode = "auto"` setting in `pyproject.toml` means `async def test_*` works without decorators.

## Dependency policy

Keep dependencies minimal. Current runtime deps:
- `httpx` — async HTTP client + SSE streaming
- `click` — CLI
- `mcp>=1.0` — MCP client (stdio/http/sse transports + `ClientSession`)

Dev-only deps (in `[dependency-groups] dev`):
- `langchain-core` — for `PiAIChatModel` (optional integration)
- `pytest`, `pytest-asyncio` — test framework

Don't add runtime dependencies without a strong reason. LangChain is intentionally kept as a dev dep only — the `langchain/` subpackage is an optional integration, not a hard requirement.

## After making changes

Update `docs/AGENTS.md` with a changelog entry describing what changed and why. This keeps the AI agent context current for future sessions.

Also update `docs/internals.md` if you've changed the behavior of any module — especially `_StreamProcessor`, `MCPClient`, `MCPHub`, or the auth flow.
