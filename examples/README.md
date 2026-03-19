# piai Examples

Make sure you've logged in first:

```bash
piai login
```

---

## Example 1 — piai native agent + MCP filesystem

`mcp_filesystem_agent.py` — piai's built-in `agent()` loop connected to the MCP filesystem server. The model autonomously explores a directory, reads files, and summarizes what it finds.

```bash
python examples/mcp_filesystem_agent.py
```

**What it shows:**
- `agent()` autonomous loop
- `MCPServer.stdio()` to spawn an MCP subprocess
- `on_event` streaming callback
- `ThinkingDeltaEvent` for reasoning output

---

## Example 2 — LangChain + piai + MCP

`langchain_mcp_agent.py` — `PiAIChatModel` used across four patterns in one file:

| Section | What it shows |
|---------|--------------|
| `simple_example()` | `invoke` (sync) + `ainvoke` / `astream` (async) |
| `tool_calling_example()` | `bind_tools` with local Python functions |
| `piai_native_with_mcp()` | piai `agent()` + MCP (simplest MCP path) |
| `langchain_react_agent()` | LangChain ReAct agent + MCP tools (full stack) |

```bash
python examples/langchain_mcp_agent.py

# Section 4 (ReAct agent) needs langchain:
uv add langchain
```

---

## Example 3 — Autonomous binary analysis with radare2

`radare2_binary_analysis.py` — piai agent + r2mcp for autonomous reverse engineering. The model opens the binary, runs analysis, decompiles JNI functions, traces xrefs, and produces a full markdown report.

```bash
# Install r2mcp first:
r2pm -ci r2mcp

python examples/radare2_binary_analysis.py /path/to/binary.so
```

**What it shows:**
- Multi-step autonomous agent loop
- Tool call logging in `on_event`
- Detailed system prompt driving structured analysis

---

## Example 4 — Autonomous binary analysis with IDA Pro

`ida_binary_analysis.py` — same as example 3 but using IDA Pro's MCP server instead of radare2. Supports both stdio (`ida-mcp`) and HTTP transport.

```bash
# With ida-mcp stdio (IDA must have the binary open):
python examples/ida_binary_analysis.py /path/to/binary.so

# With IDA HTTP MCP server running on :13337:
python examples/ida_binary_analysis.py /path/to/binary.so --http
```

---

## Notes

- All examples use `gpt-5.1-codex-mini` by default — change `model_id` to any model your ChatGPT Plus/Pro plan supports
- **`temperature` is not supported** by the ChatGPT backend — do not pass it in `options`
- MCP filesystem server is fetched automatically via `npx -y @modelcontextprotocol/server-filesystem`
