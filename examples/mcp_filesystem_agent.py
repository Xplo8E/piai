"""
Example 1: piai native agent + MCP filesystem server

Uses piai's built-in agent() loop with the official MCP filesystem server
to let the model read, explore, and summarize files autonomously.

Requirements:
    uv add pi-ai-py
    npm install -g @modelcontextprotocol/server-filesystem   # or use npx

Run:
    python examples/mcp_filesystem_agent.py
"""

import asyncio
import logging

from piai import agent
from piai.mcp import MCPServer
from piai.types import Context, TextDeltaEvent, ThinkingDeltaEvent, UserMessage

# Uncomment to see debug logs from the agent/MCP layer
# logging.basicConfig(level=logging.DEBUG)

TARGET_DIR = "/tmp"  # Change to any directory you want the agent to explore


def on_event(event):
    """Live streaming callback — print text and reasoning as they arrive."""
    if isinstance(event, TextDeltaEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ThinkingDeltaEvent):
        print(f"\033[2m{event.thinking}\033[0m", end="", flush=True)  # dim for reasoning


async def main():
    ctx = Context(
        system_prompt=(
            "You are a helpful file system explorer. "
            "Use the available tools to explore the directory the user specifies. "
            "Always list files first, then read relevant ones, then summarize your findings."
        ),
        messages=[
            UserMessage(
                content=(
                    f"Explore {TARGET_DIR} and give me a summary of what's in there. "
                    "List the files, read a few interesting ones, and explain what you find."
                )
            )
        ],
    )

    print(f"Starting agent — exploring {TARGET_DIR!r} ...\n")
    print("─" * 60)

    result = await agent(
        model_id="gpt-5.1-codex-mini",
        context=ctx,
        mcp_servers=[
            # npx automatically downloads the server if not installed
            MCPServer.stdio(f"npx -y @modelcontextprotocol/server-filesystem {TARGET_DIR}"),
        ],
        options={
            "reasoning_effort": "medium",
        },
        max_turns=15,
        on_event=on_event,
        require_all_servers=True,   # fail fast if filesystem server can't start
        connect_timeout=30.0,
        tool_result_max_chars=16_000,
    )

    print("\n" + "─" * 60)
    print(f"\nAgent finished. Stop reason: {result.stop_reason}")
    if result.usage:
        print(f"Tokens — in: {result.usage.get('input', '?')}, out: {result.usage.get('output', '?')}")


if __name__ == "__main__":
    asyncio.run(main())
