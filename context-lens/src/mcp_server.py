#!/usr/bin/env python3
"""MCP server for Context Lens."""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from query.smart import run_fix, run_ask, run_plan
from indexer.core import run_index


class MCPServer:
    """MCP server exposing lens fix/ask/plan as tools."""

    def __init__(self):
        self.tools = {
            "lens_fix": {
                "name": "lens_fix",
                "description": "Select relevant code for a bug fix or implementation task. Auto-indexes if needed. Returns selected code with fix instructions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "What needs to be fixed or implemented."
                        },
                        "error_log": {
                            "type": "string",
                            "description": "Optional error traceback or log."
                        },
                        "repo_path": {
                            "type": "string",
                            "description": "Path to repo root. Default: current directory.",
                            "default": "."
                        }
                    },
                    "required": ["task"]
                }
            },
            "lens_ask": {
                "name": "lens_ask",
                "description": "Answer a question about the codebase. Auto-indexes if needed. Returns relevant code with explanation instructions. No edits.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "What you want to know about the codebase."
                        },
                        "error_log": {
                            "type": "string",
                            "description": "Optional error traceback or log."
                        },
                        "repo_path": {
                            "type": "string",
                            "description": "Path to repo root. Default: current directory.",
                            "default": "."
                        }
                    },
                    "required": ["question"]
                }
            },
            "lens_plan": {
                "name": "lens_plan",
                "description": "Create an implementation plan for a task. Auto-indexes if needed. Returns relevant code with planning instructions. No edits.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "What needs to be built or changed."
                        },
                        "error_log": {
                            "type": "string",
                            "description": "Optional error traceback or log."
                        },
                        "repo_path": {
                            "type": "string",
                            "description": "Path to repo root. Default: current directory.",
                            "default": "."
                        }
                    },
                    "required": ["task"]
                }
            },
        }

    async def handle_request(self, request: dict) -> dict:
        """Handle a JSON-RPC request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "context-lens", "version": "2.0.0"}
                }
            elif method == "notifications/initialized":
                return None
            elif method == "tools/list":
                result = {"tools": list(self.tools.values())}
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = await self.call_tool(tool_name, arguments)
            else:
                return {
                    "jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }

            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32603, "message": str(e)}
            }

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool."""
        loop = asyncio.get_event_loop()

        if tool_name == "lens_fix":
            result = await loop.run_in_executor(None, lambda: run_fix(
                arguments["task"],
                repo_path=arguments.get("repo_path", "."),
                error_log=arguments.get("error_log"),
            ))
        elif tool_name == "lens_ask":
            result = await loop.run_in_executor(None, lambda: run_ask(
                arguments["question"],
                repo_path=arguments.get("repo_path", "."),
                error_log=arguments.get("error_log"),
            ))
        elif tool_name == "lens_plan":
            result = await loop.run_in_executor(None, lambda: run_plan(
                arguments["task"],
                repo_path=arguments.get("repo_path", "."),
                error_log=arguments.get("error_log"),
            ))
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

        return {"content": [{"type": "text", "text": result}]}

    async def run(self):
        """Run the MCP server using stdio transport."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, asyncio.get_event_loop())

        while True:
            try:
                header = await reader.readline()
                if not header:
                    break
                if header.startswith(b"Content-Length:"):
                    content_length = int(header.decode().split(":")[1].strip())
                    await reader.readline()
                    content = await reader.read(content_length)
                    request = json.loads(content.decode())
                    response = await self.handle_request(request)
                    if response is not None:
                        response_bytes = json.dumps(response).encode()
                        h = f"Content-Length: {len(response_bytes)}\r\n\r\n"
                        writer.write(h.encode() + response_bytes)
                        await writer.drain()
            except Exception as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.stderr.flush()


async def main():
    server = MCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
