"""
agent() — autonomous agentic loop with MCP tool support.

Connects to MCP servers, discovers tools, runs the model in a loop,
executes tool calls, and continues until the model stops or max_turns is reached.

No LangChain, no LangGraph, no mcpo required. Just piai + MCP.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from .mcp.hub import MCPHub
from .mcp.server import MCPServer
from .stream import stream
from .types import (
    AssistantMessage,
    Context,
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    TextDeltaEvent,
    ToolCall,
    ToolCallContent,
    ToolCallEndEvent,
    ToolResultMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

OPENAI_CODEX_PROVIDER = "openai-codex"


async def agent(
    model_id: str,
    context: Context,
    mcp_servers: list[MCPServer],
    options: dict[str, Any] | None = None,
    provider_id: str = OPENAI_CODEX_PROVIDER,
    max_turns: int = 20,
    on_event: Callable[[StreamEvent], None] | None = None,
) -> AssistantMessage:
    """
    Run an autonomous agentic loop using MCP servers for tools.

    Connects to all provided MCP servers, discovers their tools, injects them
    into the context, and runs the model in a loop — executing tool calls and
    feeding results back — until the model stops or max_turns is reached.

    Args:
        model_id:    Model to use, e.g. "gpt-5.1-codex-mini"
        context:     Initial conversation context (messages + optional system_prompt)
        mcp_servers: List of MCPServer configs. All are connected concurrently.
        options:     Provider options (reasoning_effort, session_id, etc.)
        provider_id: Defaults to "openai-codex"
        max_turns:   Safety limit on agentic loop iterations. Default: 20.
        on_event:    Optional callback called for every StreamEvent (for live output).

    Returns:
        The final AssistantMessage after the model stops.

    Example:
        from piai import agent
        from piai.mcp import MCPServer
        from piai.types import Context, UserMessage

        ctx = Context(messages=[UserMessage(content="Analyze /lib/target.so")])

        result = await agent(
            model_id="gpt-5.1-codex-mini",
            context=ctx,
            mcp_servers=[
                MCPServer.stdio("r2pm -r r2mcp"),
                MCPServer.stdio("npx @modelcontextprotocol/server-filesystem /tmp"),
            ],
            on_event=lambda e: print(e) if isinstance(e, TextDeltaEvent) else None,
        )
        print(result)
    """
    async with MCPHub(mcp_servers) as hub:
        tools = hub.all_tools()
        if not tools:
            logger.warning("No tools discovered from MCP servers. Running without tools.")

        # Inject discovered tools into context
        ctx = Context(
            messages=list(context.messages),
            system_prompt=context.system_prompt,
            tools=tools if tools else context.tools,
        )

        opts = dict(options or {})
        final_message: AssistantMessage | None = None

        for turn in range(max_turns):
            logger.debug("Agent turn %d/%d", turn + 1, max_turns)

            # Collect all events for this turn
            tool_calls_made: list[ToolCall] = []
            assistant_content_blocks = []
            current_text = ""
            done_event: DoneEvent | None = None

            async for event in stream(model_id, ctx, opts, provider_id):
                if on_event:
                    on_event(event)

                if isinstance(event, TextDeltaEvent):
                    current_text += event.text

                elif isinstance(event, ToolCallEndEvent):
                    tool_calls_made.append(event.tool_call)

                elif isinstance(event, DoneEvent):
                    done_event = event
                    final_message = event.message

                elif isinstance(event, ErrorEvent):
                    raise RuntimeError(
                        event.error.error_message or "piai stream error"
                    )

            if done_event is None:
                raise RuntimeError("Stream ended without a done event")

            # If no tool calls, model is done
            if not tool_calls_made:
                logger.debug("No tool calls — agent complete after %d turn(s)", turn + 1)
                break

            # Append assistant message to context
            ctx.messages.append(final_message)

            # Execute all tool calls and append results
            for tc in tool_calls_made:
                logger.debug("Calling tool %r with args: %s", tc.name, tc.input)
                try:
                    result = await hub.call_tool(tc.name, tc.input)
                    logger.debug("Tool %r returned: %s", tc.name, result[:200])
                except Exception as e:
                    result = f"Error calling tool {tc.name!r}: {e}"
                    logger.warning("Tool call failed: %s", e)

                ctx.messages.append(
                    ToolResultMessage(
                        tool_call_id=tc.id,
                        content=result,
                    )
                )

            # Continue loop — model will see tool results and respond
            logger.debug(
                "Turn %d complete: %d tool call(s) executed, continuing...",
                turn + 1,
                len(tool_calls_made),
            )

        else:
            logger.warning(
                "Agent reached max_turns=%d without stopping. Returning last message.",
                max_turns,
            )

        if final_message is None:
            raise RuntimeError("Agent loop ended without a final message")

        return final_message
