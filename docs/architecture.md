# piai — Architecture

## What is piai?

piai is a Python port of [@mariozechner/pi-ai](https://github.com/badlogic/pi-mono). It lets you use your **ChatGPT Plus/Pro subscription** to call GPT models from Python — no OpenAI API key, no per-token billing. It authenticates via the same OAuth flow the ChatGPT web app uses and streams responses from ChatGPT's internal backend.

---

## High-level flow

```
User code
  │
  ├── stream() / complete() / complete_text()   [stream.py]
  │       │
  │       ├── load credentials from auth.json   [oauth/storage.py]
  │       ├── auto-refresh if expired            [oauth/__init__.py]
  │       └── call stream_openai_codex()         [providers/openai_codex.py]
  │               │
  │               ├── build request body         [providers/message_transform.py]
  │               ├── POST /codex/responses      [chatgpt.com internal API]
  │               ├── parse SSE stream           [_StreamProcessor]
  │               └── yield typed StreamEvents   [types.py]
  │
  ├── agent()                                    [agent.py]
  │       │
  │       ├── MCPHub.connect()                   [mcp/hub.py]
  │       │     ├── MCPClient(server1).connect() [mcp/client.py]
  │       │     ├── MCPClient(server2).connect()
  │       │     └── discover + merge all tools
  │       │
  │       └── loop: stream() → tool calls → MCPHub.call_tool() → ToolResultMessage → repeat
  │
  ├── PiAIChatModel                              [langchain/chat_model.py]
  │       │
  │       └── wraps piai_stream() as LangChain BaseChatModel
  │
  └── CLI (piai login/run/status/...)            [cli.py]
          │
          └── OAuth PKCE flow                    [oauth/openai_codex.py]
                  ├── local HTTP server :1455    [_CallbackServer]
                  ├── browser → auth.openai.com
                  └── exchange code → tokens
```

---

## Directory structure

```
src/piai/
├── __init__.py              # Public API exports
├── types.py                 # All data types: Context, messages, stream events
├── stream.py                # Entry points: stream(), complete(), complete_text()
├── agent.py                 # Autonomous agentic loop with MCP support
├── cli.py                   # CLI commands via Click
├── oauth/
│   ├── __init__.py          # Provider registry + get_oauth_api_key()
│   ├── types.py             # OAuthCredentials, OAuthProviderInterface
│   ├── storage.py           # auth.json read/write
│   ├── pkce.py              # PKCE verifier + challenge (RFC 7636)
│   └── openai_codex.py      # ChatGPT Plus OAuth login + token refresh
├── mcp/
│   ├── __init__.py          # Exports MCPServer, MCPClient, MCPHub
│   ├── server.py            # MCPServer config dataclass (stdio/http/sse factories)
│   ├── client.py            # MCPClient — persistent session per MCP server
│   └── hub.py               # MCPHub — multi-server manager
├── langchain/
│   └── chat_model.py        # PiAIChatModel — LangChain BaseChatModel adapter
└── providers/
    ├── message_transform.py # Context → OpenAI Responses API format
    └── openai_codex.py      # SSE streaming to chatgpt.com/backend-api
```

---

## Key design decisions

### Why not the public OpenAI API?
The public API charges per token. This library uses ChatGPT's internal backend (`chatgpt.com/backend-api/codex/responses`) which is covered by the Plus/Pro subscription. The trade-off: it uses internal endpoints that could change without notice.

### OpenAI Responses API vs Chat Completions API
The internal backend uses the **Responses API** format, which differs from the Chat Completions API:
- System prompt → top-level `instructions` field (not in messages array)
- Tool calls → separate `function_call` items (not inside message content)
- Tool results → `function_call_output` items
- Streaming events are named differently (e.g. `response.output_text.delta`)

### auth.json format
Credentials use **camelCase keys** (`accountId`, `expires` in ms) to stay compatible with the JS SDK's auth.json. If you've logged in with the JS CLI, the same file works here — no re-login needed.

### Stream processor state machine
The SSE stream is processed by `_StreamProcessor` which mirrors the JS `processResponsesStream()` state machine exactly. It tracks:
- `current_item` — the active output item (reasoning / message / function_call)
- `current_block` — the active content block within that item

This is necessary because the Responses API sends items and blocks as separate events that must be correlated.

SSE line endings are normalized from CRLF/CR to LF before parsing to handle any server variations.

### Auto token refresh
Credentials are refreshed automatically with a **5-minute buffer** before expiry. This prevents race conditions where the token expires between the credential check and the actual API call.

### MCP: AsyncExitStack for stateful sessions
MCP servers like `r2mcp` and `ida-mcp` are stateful — you open a file in one call, analyze it in the next. `MCPClient` uses `AsyncExitStack` to keep the subprocess/connection alive for the entire agent session. Without it, each tool call would spawn a fresh process and lose all state.

### MCP tool name collision
If two servers expose the same tool name, **both** are namespaced: `s1__tool_name` and `s2__tool_name`. The original unnamespaced name continues to route to the first server for backward compatibility. A warning is logged.

### Tool merging in agent()
`agent()` merges MCP-discovered tools with any pre-existing `context.tools`. MCP tools take priority on name conflicts (de-duplicated by name). This allows users to pass fallback tools in the context that coexist with MCP tools.

### LangChain adapter
`PiAIChatModel` converts LangChain message types to piai types and back. The sync `_generate` / `_stream` methods use `asyncio.run()` (standard LangChain pattern). For Jupyter/async use, call `ainvoke` / `astream` directly.

---

## Adding a new OAuth provider

1. Create `src/piai/oauth/<provider_name>.py`
2. Implement `OAuthProviderInterface` (see `oauth/types.py`):
   - `id: str` — unique string identifier
   - `name: str` — human-readable name
   - `login(callbacks) -> OAuthCredentials`
   - `refresh_token(credentials) -> OAuthCredentials`
   - `get_api_key(credentials) -> str`
3. Register it in `oauth/__init__.py`:
   ```python
   from .my_provider import MyProvider
   register_oauth_provider(MyProvider())
   ```
4. Optionally add a new streaming provider in `providers/` and wire it up in `stream.py`

---

## Adding a new streaming provider

1. Create `src/piai/providers/<provider_name>.py`
2. Implement an async generator that yields `StreamEvent` instances
3. In `stream.py`, route to your provider based on `provider_id`

---

## JS SDK correspondence

Every module mirrors a JS counterpart:

| Python | JavaScript |
|--------|-----------|
| `oauth/pkce.py` | `src/utils/oauth/pkce.ts` |
| `oauth/types.py` | `src/utils/oauth/types.ts` |
| `oauth/storage.py` | `src/cli.ts` (credential persistence) |
| `oauth/openai_codex.py` | `src/utils/oauth/openai-codex.ts` |
| `providers/message_transform.py` | `src/providers/openai-responses-shared.ts` + `transform-messages.ts` |
| `providers/openai_codex.py` | `src/providers/openai-codex-responses.ts` |
| `stream.py` | `src/stream.ts` |
| `types.py` | `src/types.ts` |
| `cli.py` | `src/cli.ts` |
| `agent.py` | (Python-native, no direct JS equivalent) |
| `mcp/` | (Python-native MCP integration) |
| `langchain/` | (Python-native LangChain adapter) |
