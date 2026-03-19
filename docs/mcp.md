# MCP Integration

piai has a native MCP (Model Context Protocol) client built in. No LangChain, no mcpo, no manual tool wrappers — just pass your MCP server configs and the agent handles everything automatically.

---

## Quick start

```python
import asyncio
from piai import agent
from piai.mcp import MCPServer
from piai.types import Context, UserMessage

ctx = Context(messages=[UserMessage(content="Analyze /lib/target.so")])

result = await agent(
    model_id="gpt-5.1-codex-mini",
    context=ctx,
    mcp_servers=[
        MCPServer.stdio("r2pm -r r2mcp"),
    ],
)
print(result)
```

That's it. piai will:
1. Spawn the MCP server subprocess
2. Auto-discover all tools it exposes
3. Run the model in a loop, executing tool calls as requested
4. Return the final `AssistantMessage` when the model stops

---

## MCPServer transports

### stdio — local subprocess

Spawns a process and communicates via stdin/stdout. Works with any MCP server that runs as a subprocess.

```python
# Simple command
MCPServer.stdio("r2pm -r r2mcp")

# Command with arguments already split
MCPServer.stdio("npx @modelcontextprotocol/server-filesystem /tmp")

# With custom env vars
MCPServer.stdio("my-server", env={"API_KEY": "abc123"})

# With explicit name (used for namespacing on tool collisions)
MCPServer.stdio("ida-mcp", name="ida")
```

### http — Streamable HTTP (modern)

Connects to an MCP server over HTTP. The recommended transport for remote or long-running servers.

```python
MCPServer.http("http://127.0.0.1:13337/mcp")
MCPServer.http("http://127.0.0.1:13337/mcp", name="ida")
MCPServer.http("https://my-server.example.com/mcp", headers={"Authorization": "Bearer token"})
```

### sse — Server-Sent Events (legacy)

For older MCP servers that use the SSE transport instead of Streamable HTTP.

```python
MCPServer.sse("http://localhost:9000/sse")
MCPServer.sse("http://localhost:9000/sse", headers={"Authorization": "Bearer token"})
```

---

## Multiple MCP servers

Pass an array of servers. piai connects to all of them concurrently, merges their tools into a flat list, and routes each tool call to the correct server automatically. The model picks whatever tool fits the task — it doesn't know or care which server it came from.

```python
result = await agent(
    model_id="gpt-5.1-codex-mini",
    context=ctx,
    mcp_servers=[
        MCPServer.stdio("r2pm -r r2mcp"),                           # radare2 tools
        MCPServer.stdio("npx @modelcontextprotocol/server-filesystem /tmp"),  # filesystem
        MCPServer.http("http://127.0.0.1:13337/mcp", name="ida"),   # IDA Pro
    ],
)
```

### Tool name collisions

If two servers expose a tool with the same name, the second one is prefixed with the server name:

```
server1 exposes: read_file       → registered as: read_file
server2 exposes: read_file       → registered as: server2__read_file
```

A warning is logged when this happens. You can set explicit names on servers to control the prefix:

```python
MCPServer.stdio("my-server", name="myserver")   # collision → myserver__tool_name
```

---

## agent() options

```python
result = await agent(
    model_id="gpt-5.1-codex-mini",     # any supported model
    context=ctx,                         # Context with messages + optional system_prompt
    mcp_servers=[...],                   # list of MCPServer configs
    options={                            # passed to piai stream()
        "reasoning_effort": "medium",    # low / medium / high
        "session_id": "my-session",      # optional session continuity
    },
    provider_id="openai-codex",          # default, don't need to set
    max_turns=20,                        # safety limit on loop iterations (default: 20)
    on_event=my_callback,                # optional: called for every StreamEvent
)
```

### Live streaming with on_event

```python
from piai.types import TextDeltaEvent, ToolCallEndEvent

def on_event(event):
    if isinstance(event, TextDeltaEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolCallEndEvent):
        print(f"\n[tool] {event.tool_call.name}({event.tool_call.input})")

result = await agent(..., on_event=on_event)
```

---

## Real-world examples

### Binary analysis with radare2

```python
from piai import agent
from piai.mcp import MCPServer
from piai.types import Context, UserMessage

ctx = Context(
    system_prompt="You are an expert ARM64 reverse engineer.",
    messages=[UserMessage(content="Analyze /path/to/lib.so and report all JNI functions.")],
)

result = await agent(
    model_id="gpt-5.1-codex-mini",
    context=ctx,
    mcp_servers=[MCPServer.stdio("r2pm -r r2mcp")],
    options={"reasoning_effort": "medium"},
    max_turns=30,
)
```

### Binary analysis with IDA Pro (stdio)

```python
# ida-mcp runs headless IDA Pro, no GUI needed
result = await agent(
    model_id="gpt-5.1-codex-mini",
    context=ctx,
    mcp_servers=[MCPServer.stdio("ida-mcp", name="ida")],
    options={"reasoning_effort": "medium"},
    max_turns=40,
)
```

### Binary analysis with IDA Pro (HTTP server)

```python
# Start IDA MCP HTTP server first:
#   ida-mcp serve-http --port 13337
result = await agent(
    model_id="gpt-5.1-codex-mini",
    context=ctx,
    mcp_servers=[MCPServer.http("http://127.0.0.1:13337/mcp", name="ida")],
)
```

### Filesystem operations

```python
MCPServer.stdio("npx @modelcontextprotocol/server-filesystem /home/user/projects")
```

### Web search + code analysis together

```python
mcp_servers=[
    MCPServer.stdio("npx @modelcontextprotocol/server-brave-search"),
    MCPServer.stdio("r2pm -r r2mcp"),
]
```

---

## Architecture

```
agent()
  │
  ├── MCPHub.connect()          ← connects all servers concurrently
  │     ├── MCPClient(server1)  ← persistent stdio/http/sse session
  │     ├── MCPClient(server2)
  │     └── ...
  │
  ├── hub.all_tools()           ← merged flat tool list → Context.tools
  │
  └── loop:
        stream() → tool calls → hub.call_tool() → ToolResultMessage → continue
                → stop → return AssistantMessage
```

**Why MCPClient uses AsyncExitStack:**
MCP servers like `r2mcp` and `ida-mcp` are stateful — you open a file in one call, analyze it in the next. `AsyncExitStack` keeps the subprocess/connection alive for the entire agent session. Without it, each tool call would spawn a fresh process and lose all state.

---

## Using MCPClient / MCPHub directly

If you need lower-level access:

```python
from piai.mcp import MCPClient, MCPHub, MCPServer

# Single server
async with MCPClient(MCPServer.stdio("r2pm -r r2mcp")) as client:
    tools = await client.list_tools()
    result = await client.call_tool("open_file", {"file_path": "/lib/target.so"})
    print(result)

# Multiple servers
async with MCPHub([
    MCPServer.stdio("r2pm -r r2mcp"),
    MCPServer.stdio("ida-mcp", name="ida"),
]) as hub:
    print(hub.all_tools())
    result = await hub.call_tool("open_file", {"file_path": "/lib/target.so"})
```
