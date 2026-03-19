# piai — Agent Context

This file is the starting point for any AI-assisted work on piai. Read this first before making any changes. It is kept up to date with every significant modification.

---

## What this project is

**piai** is a Python library that lets you use your ChatGPT Plus/Pro subscription to call GPT models without paying per-token API fees. It authenticates via OAuth (same flow as the ChatGPT web app) and streams responses from ChatGPT's internal backend.

- PyPI package: `piai`
- Import: `from piai import stream, complete, complete_text`
- CLI: `piai login`, `piai run "prompt"`, `piai status`
- GitHub: https://github.com/Xplo8E/piai
- Python: 3.12+, built with `uv`

---

## Project layout

```
src/piai/
├── __init__.py              # Public exports
├── types.py                 # Context, messages, stream events (all data types)
├── stream.py                # stream() / complete() / complete_text() entry points
├── cli.py                   # CLI (Click): login, logout, list, status, run
├── oauth/
│   ├── __init__.py          # Provider registry + get_oauth_api_key() with auto-refresh
│   ├── types.py             # OAuthCredentials, OAuthProviderInterface ABC
│   ├── storage.py           # auth.json read/write (CWD, camelCase keys)
│   ├── pkce.py              # RFC 7636 PKCE: verifier + challenge
│   └── openai_codex.py      # ChatGPT Plus OAuth login + refresh
├── agent.py                 # agent() — autonomous agentic loop with MCP
├── mcp/
│   ├── __init__.py          # exports MCPServer, MCPClient, MCPHub
│   ├── server.py            # MCPServer config (stdio/http/sse factory methods)
│   ├── client.py            # MCPClient — persistent connection to one MCP server
│   └── hub.py               # MCPHub — manages N servers, merges tools, routes calls
└── providers/
    ├── message_transform.py # Context → OpenAI Responses API wire format
    └── openai_codex.py      # SSE streaming + _StreamProcessor state machine
tests/
    test_pkce.py
    test_oauth_codex.py
    test_message_transform.py
docs/
    architecture.md          # Design overview and flow diagrams
    internals.md             # Per-module deep-dive
    contributing.md          # Setup and contribution guide
    AGENTS.md                 # This file
```

---

## MCP integration

piai has a native MCP client layer. No LangChain, no mcpo, no manual tool wrappers.

```python
from piai import agent
from piai.mcp import MCPServer
from piai.types import Context, UserMessage

ctx = Context(messages=[UserMessage(content="Analyze /lib/target.so")])

result = await agent(
    model_id="gpt-5.1-codex-mini",
    context=ctx,
    mcp_servers=[
        MCPServer.stdio("r2pm -r r2mcp"),                          # spawns subprocess
        MCPServer.stdio("npx @modelcontextprotocol/server-filesystem /tmp"),
        MCPServer.http("http://localhost:9000/mcp"),                # Streamable HTTP
        MCPServer.sse("http://localhost:9000/sse"),                 # legacy SSE
    ],
    options={"reasoning_effort": "medium"},
    max_turns=20,                                                   # safety limit
    on_event=lambda e: print(e),                                    # optional live output
)
```

**How it works:**
1. `MCPHub` connects to all servers concurrently
2. Tools are auto-discovered via `list_tools` from each server
3. All tools merged into a flat list, injected into `Context.tools`
4. `agent()` runs `stream()` in a loop, executing tool calls via `MCPHub.call_tool()`
5. Tool results appended as `ToolResultMessage`, loop continues until model stops

**Tool name collisions:** If two servers expose the same tool name, the second is namespaced: `servername__toolname`. A warning is logged.

**Key classes:**
- `MCPServer` — config only, no connection. Factory: `.stdio()`, `.http()`, `.sse()`
- `MCPClient` — one persistent session (uses `AsyncExitStack` to keep transport alive)
- `MCPHub` — async context manager over N clients, handles connect/discover/route/close

---

## Critical invariants (do not break these)

1. **auth.json keys are camelCase** — `accountId`, `expires` (in ms). Must stay compatible with the JS SDK.
2. **`expires` is Unix milliseconds** — `int(time.time() * 1000) + expires_in * 1000`.
3. **JWT base64 padding** — JWT strips `=` padding. Always re-add: `payload + "=" * (4 - len(payload) % 4)`.
4. **Stream processor event order** — `_StreamProcessor` in `providers/openai_codex.py` must handle SSE events in the exact sequence the Responses API sends. See `docs/internals.md` for the full event table.
5. **No retry on usage limit** — Skip retries when `"usage limit"` appears in the error message.
6. **`instructions` always present** — Defaults to `"You are a helpful assistant."` if no system prompt.
7. **PKCE base64url has no padding** — Strip all `=` characters after encoding.

---

## How to run tests

```bash
# Always use the local venv directly (avoids pi-mono workspace venv conflict)
.venv/bin/python3 -m pytest tests/ -v
```

---

## Supported models

Models are passed directly to the ChatGPT backend. Only models available on ChatGPT Plus/Pro work:

| Model ID | Notes |
|----------|-------|
| `gpt-5.1-codex-mini` | Fast, default |
| `gpt-5.1` | More capable |
| `gpt-5.1-codex-max` | |
| `gpt-5.2`, `gpt-5.2-codex` | |
| `gpt-5.3-codex`, `gpt-5.3-codex-spark` | |
| `gpt-5.4` | |

**Do not use** `gpt-4o`, `o3`, `o4-mini` etc. — those are public API models, not available on this backend.

---

## Options reference

```python
options = {
    "session_id": "my-session",      # → prompt_cache_key (enables caching)
    "reasoning_effort": "high",      # low / medium / high / xhigh (clamped per model)
    "reasoning_summary": "auto",     # auto / concise / detailed / off
    "text_verbosity": "medium",      # low / medium / high
    "temperature": 0.7,
    "base_url": "...",               # Override backend URL (testing only)
}
```

---

## Changelog

### 2026-03-19 — Initial port + gap fixes
- Ported entire openai-codex provider from JS SDK (@mariozechner/pi-ai)
- OAuth PKCE flow, token refresh, auth.json storage
- SSE stream processor state machine (`_StreamProcessor`) mirroring JS `processResponsesStream()`
- Added `_clamp_reasoning_effort()` (Fix 1)
- Added usage limit retry exclusion (Fix 2)
- Full `_StreamProcessor` rewrite to faithful JS state machine port (Fix 3)
- `response.failed` extracts `incomplete_details.reason` (Fix 4)
- Fixed usage calculation: subtracts `cached_tokens` from `input_tokens`
- Renamed package from `pyai` → `piai` (PyPI name + module + CLI)
- Created `docs/` folder with architecture, internals, contributing, and AGENTS.md
