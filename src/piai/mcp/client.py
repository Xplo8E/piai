"""
MCPClient — manages a persistent connection to one MCP server.

Uses AsyncExitStack to keep the transport alive across multiple tool calls,
which is critical for stateful servers like r2mcp (open_file → analyze →
list_exports all need to hit the same radare2 process).
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..types import Tool
from .server import MCPServer

logger = logging.getLogger(__name__)


class MCPClient:
    """
    Persistent connection to a single MCP server.

    Usage:
        client = MCPClient(MCPServer.stdio("r2pm -r r2mcp"))
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("open_file", {"file_path": "/lib.so"})
        await client.close()

    Or as async context manager:
        async with MCPClient(server) as client:
            tools = await client.list_tools()
    """

    def __init__(self, server: MCPServer) -> None:
        self.server = server
        self._session: ClientSession | None = None
        self._exit_stack = AsyncExitStack()
        self._connected = False

    async def connect(self) -> None:
        """Connect to the MCP server and initialize the session."""
        if self._connected:
            return

        if self.server.transport == "stdio":
            await self._connect_stdio()
        elif self.server.transport == "http":
            await self._connect_http()
        elif self.server.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self.server.transport!r}")

        await self._session.initialize()
        self._connected = True
        logger.debug("Connected to MCP server: %s", self.server)

    async def _connect_stdio(self) -> None:
        params = StdioServerParameters(
            command=self.server.command,
            args=self.server.args,
            env=self.server.env,
        )
        transport = await self._exit_stack.enter_async_context(stdio_client(params))
        read, write = transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

    async def _connect_http(self) -> None:
        from mcp.client.streamable_http import streamablehttp_client

        transport = await self._exit_stack.enter_async_context(
            streamablehttp_client(self.server.url, headers=self.server.headers)
        )
        read, write, _ = transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

    async def _connect_sse(self) -> None:
        from mcp.client.sse import sse_client

        transport = await self._exit_stack.enter_async_context(
            sse_client(self.server.url, headers=self.server.headers)
        )
        read, write = transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

    async def list_tools(self) -> list[Tool]:
        """
        Discover all tools from this server.

        Returns piai Tool objects ready to pass into Context.tools.
        """
        self._ensure_connected()
        response = await self._session.list_tools()
        tools = []
        for t in response.tools:
            tools.append(Tool(
                name=t.name,
                description=t.description or "",
                parameters=t.inputSchema if isinstance(t.inputSchema, dict) else {},
            ))
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """
        Call a tool on this server.

        Returns the tool result as a string (concatenated text blocks).
        Raises RuntimeError if the tool reports an error.
        """
        self._ensure_connected()
        result = await self._session.call_tool(name, arguments=arguments)

        if result.isError:
            # Extract error text
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
            raise RuntimeError(f"Tool {name!r} returned error: {' '.join(parts) or 'unknown error'}")

        # Concatenate all text content blocks
        parts = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts)

    async def close(self) -> None:
        """Shut down the connection cleanly."""
        if self._connected:
            await self._exit_stack.aclose()
            self._connected = False
            self._session = None

    def _ensure_connected(self) -> None:
        if not self._connected or self._session is None:
            raise RuntimeError(
                f"MCPClient not connected to {self.server}. Call connect() first."
            )

    # ------------------------------------------------------------------ #
    # Async context manager                                               #
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
