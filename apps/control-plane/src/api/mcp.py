import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from common.mcp.mcp_bridge import mcp_bridge

router = APIRouter(prefix="/v1/mcp", tags=["Model Context Protocol (MCP) Gateway Bridge"])


@router.get("/sse", summary="MCP Server-Sent Events (SSE) Stream")
async def mcp_sse_stream(request: Request):
    """
    Establishes SSE Connection for MCP Clients (Cursor, Antigravity, Claude Desktop).
    """
    async def event_generator():
        # Endpoint announcement event
        yield "event: endpoint\ndata: /v1/mcp/messages\n\n"
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(15)
            yield "event: ping\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/messages", summary="MCP JSON-RPC Tool Execution Message Endpoint")
async def mcp_messages(request: Request):
    """
    Receives MCP JSON-RPC 2.0 requests from MCP Clients and executes AIP Model tools.
    """
    payload = await request.json()
    response = await mcp_bridge.handle_jsonrpc(payload)
    return JSONResponse(content=response)


@router.get("/tools", summary="List Available MCP Tools")
async def list_mcp_tools():
    """
    Returns the list of exposed AIP Model tools for MCP protocol.
    """
    return {
        "object": "list",
        "protocol_version": "2024-11-05",
        "tools": mcp_bridge.list_tools()
    }
