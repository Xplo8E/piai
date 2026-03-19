"""
Autonomous binary analysis agent using:
- piai agent() — native agentic loop
- MCPServer.stdio() — r2mcp spawned directly (no mcpo needed)
- Tools auto-discovered from r2mcp, no manual wrappers

Usage:
    uv run python test_mcp_agent.py
"""

import asyncio
from piai import agent
from piai.mcp import MCPServer
from piai.types import Context, UserMessage, TextDeltaEvent, ToolCallEndEvent

LIB = "/Users/vinay/projects/fuzzer/data/jobs/job_20260312_164531_c29f079a/extracted/lib/arm64-v8a/libblogfuzz.so"

SYSTEM_PROMPT = f"""You are an expert ARM64 Android binary reverse engineer.

Your task: autonomously analyze the native library at:
  {LIB}

Work through these steps in order:
1. Call open_file with the library path
2. Call show_info to get binary metadata
3. Call analyze to run full analysis
4. Call list_exports to find all exported symbols — focus on Java_* JNI functions
5. For each JNI function: call decompile_function to understand what it does
6. Call list_imports to see what external functions it uses
7. Call list_strings to find interesting strings (URLs, keys, suspicious content)
8. For interesting functions, call xrefs_to to see who calls them
9. Call list_sections for binary layout

After gathering all data, write a comprehensive markdown report covering:
- Binary metadata (arch, size, format)
- All JNI functions with decompiled code and what each does
- Other notable exported functions
- Imports and external dependencies
- Interesting strings
- Overall assessment: what does this library do?

Be thorough and autonomous. Keep going until you have a complete picture."""


def on_event(event):
    if isinstance(event, ToolCallEndEvent):
        print(f"\n[tool] {event.tool_call.name}({event.tool_call.input})")
    elif isinstance(event, TextDeltaEvent):
        print(event.text, end="", flush=True)


async def main():
    print("[*] Starting autonomous analysis with piai + r2mcp...")
    print("=" * 60)

    ctx = Context(
        system_prompt=SYSTEM_PROMPT,
        messages=[UserMessage(content=f"Analyze {LIB} and give me a full report.")],
    )

    result = await agent(
        model_id="gpt-5.1-codex-mini",
        context=ctx,
        mcp_servers=[
            MCPServer.stdio("r2pm -r r2mcp"),
        ],
        options={"reasoning_effort": "medium"},
        on_event=on_event,
    )

    print("\n" + "=" * 60)
    print("[*] Analysis complete.")


asyncio.run(main())
