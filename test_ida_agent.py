"""
Autonomous binary analysis agent using:
- piai agent() — native agentic loop
- IDA Pro MCP server (http://127.0.0.1:13337/mcp)

Make sure IDA Pro has the target lib open and the MCP server is running
before starting this script.

Usage:
    uv run python test_ida_agent.py
"""

import asyncio
from piai import agent
from piai.mcp import MCPServer
from piai.types import Context, UserMessage, TextDeltaEvent, ToolCallEndEvent

LIB = "/Users/vinay/projects/fuzzer/data/jobs/job_20260312_164531_c29f079a/extracted/lib/arm64-v8a/libblogfuzz.so"

SYSTEM_PROMPT = f"""You are an expert ARM64 Android binary reverse engineer using IDA Pro.

The binary is already open in IDA Pro: {LIB}

Work through these steps:
1. Get a list of all functions — focus on Java_* JNI exports
2. Decompile each JNI function to understand what it does
3. Find cross-references to interesting functions
4. Look for strings — URLs, keys, magic values
5. Check imports / external calls
6. Identify any interesting non-JNI functions called internally

After gathering all data, write a comprehensive markdown report covering:
- All JNI functions with decompiled pseudocode and explanation
- Cross-references and call graph
- Interesting strings found
- External library calls / imports
- Overall assessment: what does this library do?

Be thorough and autonomous. Use whatever IDA tools are available to get a complete picture."""


def on_event(event):
    if isinstance(event, ToolCallEndEvent):
        args_preview = {
            k: (v[:80] + "..." if isinstance(v, str) and len(v) > 80 else v)
            for k, v in event.tool_call.input.items()
        }
        print(f"\n[tool] {event.tool_call.name}({args_preview})")
    elif isinstance(event, TextDeltaEvent):
        # Strip inline <thinking>...</thinking> blocks from display
        print(event.text, end="", flush=True)
    elif hasattr(event, 'type'):
        from piai.types import DoneEvent
        if isinstance(event, DoneEvent):
            print(f"\n[done: {event.reason}]")


async def main():
    print("[*] Connecting to IDA Pro MCP server (stdio: ida-mcp) ...")
    print("=" * 60)

    ctx = Context(
        system_prompt=SYSTEM_PROMPT,
        messages=[UserMessage(content=f"Analyze {LIB} and give me a full report.")],
    )

    result = await agent(
        model_id="gpt-5.1-codex-mini",
        context=ctx,
        mcp_servers=[
            MCPServer.stdio("ida-mcp", name="ida"),
        ],
        options={"reasoning_effort": "medium"},
        max_turns=40,
        on_event=on_event,
    )

    print("\n" + "=" * 60)
    print("[*] Analysis complete.")

    # Print final report if it wasn't streamed (e.g. after max_turns)
    from piai.types import TextContent
    for block in result.content:
        if isinstance(block, TextContent) and block.text:
            print("\n[FINAL REPORT]\n")
            print(block.text)


asyncio.run(main())
