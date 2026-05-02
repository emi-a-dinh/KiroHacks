#!/usr/bin/env python3
"""MCP server for Context Lens."""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from indexer.core import run_index
from storage.db import Database
from query.formatter import build_signature_map
from query.expander import build_expanded_prompt


class MCPServer:
    """Simple MCP server implementation."""
    
    def __init__(self):
        self.tools = {
            "context_index": {
                "name": "context_index",
                "description": "Index a code repository. Parses source files, extracts function/class signatures and call edges, and stores them in a local SQLite database. Supports incremental updates — only re-parses changed files. Detects moved/renamed files and preserves their index entries.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Absolute or relative path to the repository root."
                        }
                    },
                    "required": ["repo_path"]
                }
            },
            "context_query": {
                "name": "context_query",
                "description": "Generate a signature map of the indexed repository. The map lists every function, class, and method with their call relationships — compact enough to fit in context. Use it to identify which units to expand for a given task.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Natural language description of the task or question."
                        },
                        "error_log": {
                            "type": "string",
                            "description": "Optional error traceback or log output related to the task."
                        },
                        "k": {
                            "type": "integer",
                            "description": "Maximum number of code units to select for expansion. Default: 10.",
                            "default": 10
                        },
                        "index_path": {
                            "type": "string",
                            "description": "Path to the index database. Default: .context-lens/index.db in the current directory."
                        }
                    },
                    "required": ["task"]
                }
            },
            "context_expand": {
                "name": "context_expand",
                "description": "Expand selected code units into their full source code. Each unit is prefixed with its call edges (what it calls, what calls it). Optionally include 1-hop neighbors for tracing bugs across function boundaries.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "unit_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of unit IDs to expand (from the signature map)."
                        },
                        "task": {
                            "type": "string",
                            "description": "The original task description (included in the expanded prompt for context)."
                        },
                        "error_summary": {
                            "type": "string",
                            "description": "Optional short error summary to include in the expanded prompt."
                        },
                        "include_neighbors": {
                            "type": "boolean",
                            "description": "If true, also expand direct callers and callees of the selected units (1-hop). Default: false.",
                            "default": False
                        },
                        "index_path": {
                            "type": "string",
                            "description": "Path to the index database."
                        }
                    },
                    "required": ["unit_ids"]
                }
            }
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
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "context-lens",
                        "version": "1.0.0"
                    }
                }
            elif method == "notifications/initialized":
                return None  # No response for notifications
            elif method == "tools/list":
                result = {
                    "tools": list(self.tools.values())
                }
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = await self.call_tool(tool_name, arguments)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool and return the result."""
        if tool_name == "context_index":
            return await self.tool_context_index(arguments)
        elif tool_name == "context_query":
            return await self.tool_context_query(arguments)
        elif tool_name == "context_expand":
            return await self.tool_context_expand(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def tool_context_index(self, arguments: dict) -> dict:
        """Index a repository."""
        repo_path = arguments.get("repo_path", ".")
        
        # Run indexing (in thread pool to not block)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: run_index(repo_path, db_class=Database))
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result.to_dict(), indent=2)
                }
            ]
        }
    
    async def tool_context_query(self, arguments: dict) -> dict:
        """Generate a signature map."""
        task = arguments.get("task", "")
        error_log = arguments.get("error_log")
        k = arguments.get("k", 10)
        index_path = arguments.get("index_path", ".context-lens/index.db")
        
        # Check if index exists
        if not Path(index_path).exists():
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Index not found at {index_path}. Run context_index first."
                    }
                ],
                "isError": True
            }
        
        # Build signature map
        loop = asyncio.get_event_loop()
        
        def _build_map():
            with Database(index_path) as db:
                return build_signature_map(db, task, error_log, k)
        
        signature_map = await loop.run_in_executor(None, _build_map)
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": signature_map
                }
            ]
        }
    
    async def tool_context_expand(self, arguments: dict) -> dict:
        """Expand selected units."""
        unit_ids = arguments.get("unit_ids", [])
        task = arguments.get("task")
        error_summary = arguments.get("error_summary")
        include_neighbors = arguments.get("include_neighbors", False)
        index_path = arguments.get("index_path", ".context-lens/index.db")
        
        if not unit_ids:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Error: No unit_ids provided."
                    }
                ],
                "isError": True
            }
        
        # Check if index exists
        if not Path(index_path).exists():
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Index not found at {index_path}. Run context_index first."
                    }
                ],
                "isError": True
            }
        
        # Build expanded prompt
        loop = asyncio.get_event_loop()
        
        def _expand():
            with Database(index_path) as db:
                return build_expanded_prompt(db, unit_ids, task, error_summary, include_neighbors)
        
        expanded = await loop.run_in_executor(None, _expand)
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": expanded
                }
            ]
        }
    
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
                # Read header
                header = await reader.readline()
                if not header:
                    break
                
                # Parse Content-Length
                if header.startswith(b"Content-Length:"):
                    content_length = int(header.decode().split(":")[1].strip())
                    
                    # Read empty line
                    await reader.readline()
                    
                    # Read content
                    content = await reader.read(content_length)
                    request = json.loads(content.decode())
                    
                    # Handle request
                    response = await self.handle_request(request)
                    
                    if response is not None:
                        # Send response
                        response_bytes = json.dumps(response).encode()
                        header = f"Content-Length: {len(response_bytes)}\r\n\r\n"
                        writer.write(header.encode() + response_bytes)
                        await writer.drain()
            except Exception as e:
                # Log error but continue
                sys.stderr.write(f"Error: {e}\n")
                sys.stderr.flush()


async def main():
    server = MCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
