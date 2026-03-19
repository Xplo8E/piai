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
- `ThinkingDeltaEvent` for reasoning models

---

## Example 2 — LangChain + piai + MCP

`langchain_mcp_agent.py` — `PiAIChatModel` used across four patterns in one file:

| Section | What it shows |
|---------|--------------|
| `simple_example()` | `invoke` + async `astream` |
| `tool_calling_example()` | `bind_tools` with local Python functions |
| `piai_native_with_mcp()` | piai `agent()` + MCP (simplest MCP path) |
| `mcp_agent_example()` | LangChain ReAct agent + MCP tools (full stack) |

```bash
python examples/langchain_mcp_agent.py
```

**Requirements for LangChain ReAct section:**
```bash
uv add langchain
```

---

## Notes

- All examples use `gpt-5.1-codex-mini` by default — change `model_id` to any model your ChatGPT Plus/Pro plan supports
- MCP filesystem server is fetched automatically via `npx -y @modelcontextprotocol/server-filesystem`
- For real use cases replace the filesystem server with radare2, IDA, web search, or any other MCP server
