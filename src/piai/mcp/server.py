"""
MCPServer — configuration for a single MCP server.

Supports three transports:
  - stdio: spawns a local subprocess (e.g. r2pm -r r2mcp)
  - http:  connects to a Streamable HTTP MCP server
  - sse:   connects to a legacy SSE MCP server
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class MCPServer:
    """
    Configuration for one MCP server.

    Use the class methods for convenience:
        MCPServer.stdio("r2pm -r r2mcp")
        MCPServer.http("http://localhost:9000/mcp")
        MCPServer.sse("http://localhost:9000/sse")
    """

    transport: Literal["stdio", "http", "sse"]

    # stdio fields
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None

    # http / sse fields
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    # optional human-readable name used for namespacing on tool collisions
    # if not set, derived from command or url
    name: str | None = None

    # ------------------------------------------------------------------ #
    # Factory helpers                                                      #
    # ------------------------------------------------------------------ #

    @classmethod
    def stdio(
        cls,
        command: str,
        *,
        name: str | None = None,
        env: dict[str, str] | None = None,
    ) -> "MCPServer":
        """
        Spawn a local subprocess as an MCP server.

        Args:
            command: Full command string, e.g. "r2pm -r r2mcp" or "npx @modelcontextprotocol/server-filesystem /tmp"
            name:    Optional namespace name. Defaults to first word of command.
            env:     Extra environment variables. Inherits parent env if None.
        """
        parts = command.split()
        return cls(
            transport="stdio",
            command=parts[0],
            args=parts[1:],
            env=env,
            name=name or parts[0].split("/")[-1],  # last path component
        )

    @classmethod
    def http(
        cls,
        url: str,
        *,
        name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> "MCPServer":
        """
        Connect to a Streamable HTTP MCP server (modern transport).

        Args:
            url:     Base URL, e.g. "http://localhost:9000/mcp"
            name:    Optional namespace name. Defaults to hostname.
            headers: Optional HTTP headers (e.g. Authorization).
        """
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or url
        return cls(
            transport="http",
            url=url,
            headers=headers or {},
            name=name or hostname,
        )

    @classmethod
    def sse(
        cls,
        url: str,
        *,
        name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> "MCPServer":
        """
        Connect to a legacy SSE MCP server.

        Args:
            url:     SSE endpoint URL, e.g. "http://localhost:9000/sse"
            name:    Optional namespace name. Defaults to hostname.
            headers: Optional HTTP headers.
        """
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or url
        return cls(
            transport="sse",
            url=url,
            headers=headers or {},
            name=name or hostname,
        )

    def __repr__(self) -> str:
        if self.transport == "stdio":
            cmd = " ".join([self.command or ""] + self.args)
            return f"MCPServer.stdio({cmd!r}, name={self.name!r})"
        return f"MCPServer.{self.transport}({self.url!r}, name={self.name!r})"
