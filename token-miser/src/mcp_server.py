#!/usr/bin/env python3
"""MCP server for Token Miser."""

import asyncio
import json
import sys
from pathlib import Path

src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from query.smart import run_fix, run_ask, run_plan


class MCPServer:
    def __init__(self):
        self.tools = {
            "miser_fix": {
                "name": "miser_fix",
                "description": "Select relevant code for a bug fix or implementation task. Auto-indexes if needed. Returns selected code with fix instructions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "What needs to be fixed or implemented."},
                        "error_log": {"type": "string", "description": "Optional error traceback or log."},
                        "repo_path": {"type": "string", "description": "Path to repo root.", "default": "."}
                    },
                    "required": ["task"]
                }
            },
            "miser_ask": {
                "name": "miser_ask",
                "description": "Answer a question about the codebase. Auto-indexes if needed. Returns relevant code. No edits.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "What you want to know."},
                        "error_log": {"type": "string", "description": "Optional error traceback or log."},
                        "repo_path": {"type": "string", "description": "Path to repo root.", "default": "."}
                    },
                    "required": ["question"]
                }
            },
            "miser_plan": {
                "name": "miser_plan",
                "description": "Create an implementation plan. Auto-indexes if needed. Returns relevant code with planning instructions. No edits.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "What needs to be built or changed."},
                        "error_log": {"type": "string", "description": "Optional error traceback or log."},
                        "repo_path": {"type": "string", "description": "Path to repo root.", "default": "."}
                    },
                    "required": ["task"]
                }
            },
        }

    async def handle_request(self, request: dict) -> dict:
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")
        try:
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "token-miser", "version": "2.0.0"}}
            elif method == "notifications/initialized":
                return None
            elif method == "tools/list":
                result = {"tools": list(self.tools.values())}
            elif method == "tools/call":
                result = await self.call_tool(params.get("name", ""), params.get("arguments", {}))
            else:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unknown: {method}"}}
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(e)}}

    async def call_tool(self, name: str, args: dict) -> dict:
        loop = asyncio.get_event_loop()
        rp = args.get("repo_path", ".")
        if name == "miser_fix":
            r = await loop.run_in_executor(None, lambda: run_fix(args["task"], repo_path=rp, error_log=args.get("error_log")))
        elif name == "miser_ask":
            r = await loop.run_in_executor(None, lambda: run_ask(args["question"], repo_path=rp, error_log=args.get("error_log")))
        elif name == "miser_plan":
            r = await loop.run_in_executor(None, lambda: run_plan(args["task"], repo_path=rp, error_log=args.get("error_log")))
        else:
            raise ValueError(f"Unknown tool: {name}")
        return {"content": [{"type": "text", "text": r}]}

    async def run(self):
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        wt, wp = await asyncio.get_event_loop().connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
        writer = asyncio.StreamWriter(wt, wp, None, asyncio.get_event_loop())
        while True:
            try:
                header = await reader.readline()
                if not header:
                    break
                if header.startswith(b"Content-Length:"):
                    cl = int(header.decode().split(":")[1].strip())
                    await reader.readline()
                    content = await reader.read(cl)
                    resp = await self.handle_request(json.loads(content.decode()))
                    if resp is not None:
                        rb = json.dumps(resp).encode()
                        writer.write(f"Content-Length: {len(rb)}\r\n\r\n".encode() + rb)
                        await writer.drain()
            except Exception as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.stderr.flush()

async def main():
    await MCPServer().run()

if __name__ == "__main__":
    asyncio.run(main())
