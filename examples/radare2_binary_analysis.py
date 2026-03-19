"""
Example 3: Autonomous binary analysis with piai + radare2 (r2mcp)

Uses piai's native agent() loop with r2mcp to let the model autonomously
reverse engineer a native binary — open, analyze, decompile JNI functions,
find strings, and produce a report.

Requirements:
    uv add pi-ai-py
    r2pm -ci r2mcp    # install r2mcp plugin for radare2

Run:
    python examples/radare2_binary_analysis.py /path/to/your.so
"""

import asyncio
import sys

from piai import agent
from piai.mcp import MCPServer
from piai.types import Context, DoneEvent, TextDeltaEvent, ToolCallEndEvent, UserMessage

SYSTEM_PROMPT = """You are an expert ARM64 Android binary reverse engineer.

Work through these steps in order:
1. Call open_file with the library path
2. Call show_info to get binary metadata (arch, format, size)
3. Call analyze to run full analysis
4. Call list_exports to find all exported symbols — focus on Java_* JNI functions
5. For each JNI function: call decompile_function to understand what it does
6. Call list_imports to see what external functions it uses
7. Call list_strings to find interesting strings (URLs, keys, suspicious content)
8. For interesting functions, call xrefs_to to see who calls them
9. Call list_sections for binary layout

After gathering all data, write a comprehensive markdown report covering:
- Binary metadata (arch, size, format)
- All JNI functions with decompiled code and explanation
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
    elif isinstance(event, DoneEvent):
        print(f"\n[done: {event.reason}]")


async def main(lib_path: str):
    print(f"[*] Starting autonomous analysis of: {lib_path}")
    print("=" * 60)

    ctx = Context(
        system_prompt=SYSTEM_PROMPT,
        messages=[UserMessage(content=f"Analyze {lib_path} and give me a full report.")],
    )

    await agent(
        model_id="gpt-5.1-codex-mini",
        context=ctx,
        mcp_servers=[
            MCPServer.stdio("r2pm -r r2mcp"),
        ],
        options={"reasoning_effort": "medium"},
        max_turns=30,
        on_event=on_event,
    )

    print("\n" + "=" * 60)
    print("[*] Analysis complete.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/radare2_binary_analysis.py /path/to/binary.so")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
