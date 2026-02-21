"""MCP server implementation for SILC."""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from . import tools

# Create MCP server instance
server = Server("silc-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="send",
            description="Send text to a SILC session and wait for output",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "text": {"type": "string", "description": "Text to send"},
                    "timeout_ms": {
                        "type": "integer",
                        "default": 5000,
                        "description": "Wait timeout in ms",
                    },
                },
                "required": ["port", "text"],
            },
        ),
        Tool(
            name="read",
            description="Read output from a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "lines": {
                        "type": "integer",
                        "default": 100,
                        "description": "Number of lines",
                    },
                },
                "required": ["port"],
            },
        ),
        Tool(
            name="send_key",
            description="Send a special key (ctrl+c, enter, etc.) to a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "key": {
                        "type": "string",
                        "description": "Key name (ctrl+c, enter, escape, etc.)",
                    },
                },
                "required": ["port", "key"],
            },
        ),
        Tool(
            name="list_sessions",
            description="List all active SILC sessions",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="start_session",
            description="Create a new SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {
                        "type": "integer",
                        "description": "Desired port (optional)",
                    },
                    "shell": {
                        "type": "string",
                        "description": "Shell type (bash, zsh, pwsh, cmd)",
                    },
                    "cwd": {"type": "string", "description": "Working directory"},
                },
            },
        ),
        Tool(
            name="close_session",
            description="Close a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                },
                "required": ["port"],
            },
        ),
        Tool(
            name="get_status",
            description="Get status of a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                },
                "required": ["port"],
            },
        ),
        Tool(
            name="run",
            description="Execute a command with exit code capture (native shell only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "command": {"type": "string", "description": "Command to execute"},
                    "timeout_ms": {
                        "type": "integer",
                        "default": 60000,
                        "description": "Timeout in ms",
                    },
                },
                "required": ["port", "command"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a tool call."""
    result: dict = {}

    if name == "send":
        result = tools.send(
            port=arguments["port"],
            text=arguments["text"],
            timeout_ms=arguments.get("timeout_ms", 5000),
        )
    elif name == "read":
        result = tools.read(
            port=arguments["port"],
            lines=arguments.get("lines", 100),
        )
    elif name == "send_key":
        result = tools.send_key(
            port=arguments["port"],
            key=arguments["key"],
        )
    elif name == "list_sessions":
        result = {"sessions": tools.list_sessions()}
    elif name == "start_session":
        result = tools.start_session(
            port=arguments.get("port"),
            shell=arguments.get("shell"),
            cwd=arguments.get("cwd"),
        )
    elif name == "close_session":
        result = tools.close_session(port=arguments["port"])
    elif name == "get_status":
        result = tools.get_status(port=arguments["port"])
    elif name == "run":
        result = tools.run(
            port=arguments["port"],
            command=arguments["command"],
            timeout_ms=arguments.get("timeout_ms", 60000),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def run_mcp_server() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


__all__ = ["run_mcp_server", "server"]
