import os
import httpx

from mcp.server import MCPServer

JAP_API_URL = "https://justanotherpanel.com/api/v2"
JAP_API_KEY = os.environ.get("JAP_API_KEY")

mcp = MCPServer("JAP Connector")


async def jap_request(action: str, **kwargs):
    if not JAP_API_KEY:
        raise RuntimeError("JAP_API_KEY is not configured")

    payload = {
        "key": JAP_API_KEY,
        "action": action,
        **kwargs,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(JAP_API_URL, data=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_balance():
    """Get the current JAP account balance."""
    return await jap_request("balance")


@mcp.tool()
async def list_services():
    """List services available on the JAP account."""
    return await jap_request("services")


@mcp.tool()
async def get_order_status(order_id: int):
    """Get the status of an existing JAP order."""
    return await jap_request("status", order=order_id)


app = mcp.streamable_http_app()
