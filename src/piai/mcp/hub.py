"""
MCPHub — manages multiple MCP servers as one unified tool pool.

Connects to all servers concurrently, merges their tools into a flat list,
and routes tool calls to the correct server automatically.

Tool name collision handling:
  If two servers expose a tool with the same name, the second server's tool
  is prefixed with the server name: "server2__tool_name".
  A warning is logged when this happens.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..types import Tool
from .client import MCPClient
from .server import MCPServer

logger = logging.getLogger(__name__)


class MCPHub:
    """
    Multi-server MCP manager.

    Usage:
        async with MCPHub([
            MCPServer.stdio("r2pm -r r2mcp"),
            MCPServer.stdio("npx @modelcontextprotocol/server-filesystem /tmp"),
        ]) as hub:
            tools = hub.all_tools()
            result = await hub.call_tool("open_file", {"file_path": "/lib.so"})
    """

    def __init__(self, servers: list[MCPServer]) -> None:
        self._servers = servers
        self._clients: list[MCPClient] = []
        # tool_name -> MCPClient
        self._tool_registry: dict[str, MCPClient] = {}
        # piai Tool objects (merged, namespaced)
        self._tools: list[Tool] = []
        self._connected = False

    async def connect(self) -> None:
        """Connect to all servers concurrently and discover their tools."""
        if self._connected:
            return

        # Create clients
        self._clients = [MCPClient(s) for s in self._servers]

        # Connect all in parallel
        await asyncio.gather(*[c.connect() for c in self._clients])

        # Discover tools from each client and build registry
        for client in self._clients:
            try:
                tools = await client.list_tools()
            except Exception as e:
                logger.warning(
                    "Failed to list tools from %s: %s", client.server, e
                )
                continue

            for tool in tools:
                if tool.name in self._tool_registry:
                    # Collision — prefix with server name
                    server_name = (client.server.name or "server").replace("-", "_")
                    namespaced = f"{server_name}__{tool.name}"
                    logger.warning(
                        "Tool name collision: %r already registered. "
                        "Registering as %r from server %s.",
                        tool.name,
                        namespaced,
                        client.server,
                    )
                    namespaced_tool = Tool(
                        name=namespaced,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                    self._tool_registry[namespaced] = client
                    self._tools.append(namespaced_tool)
                else:
                    self._tool_registry[tool.name] = client
                    self._tools.append(tool)

        self._connected = True
        logger.debug(
            "MCPHub connected: %d server(s), %d tool(s): %s",
            len(self._clients),
            len(self._tools),
            [t.name for t in self._tools],
        )

    def all_tools(self) -> list[Tool]:
        """Return merged flat list of all tools from all servers."""
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """
        Route a tool call to the correct server and return the result.

        Args:
            name:      Tool name (possibly namespaced, e.g. "r2mcp__open_file")
            arguments: Tool arguments dict

        Raises:
            KeyError:       If tool name not found in any connected server.
            RuntimeError:   If the tool call fails.
        """
        client = self._tool_registry.get(name)
        if client is None:
            available = list(self._tool_registry.keys())
            raise KeyError(
                f"Tool {name!r} not found. Available tools: {available}"
            )

        # If namespaced, resolve to original tool name for the actual call
        original_name = name
        if "__" in name:
            server_prefix = (client.server.name or "").replace("-", "_") + "__"
            if name.startswith(server_prefix):
                original_name = name[len(server_prefix):]

        return await client.call_tool(original_name, arguments)

    async def close(self) -> None:
        """Disconnect all servers."""
        await asyncio.gather(*[c.close() for c in self._clients], return_exceptions=True)
        self._connected = False

    # ------------------------------------------------------------------ #
    # Async context manager                                               #
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "MCPHub":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
