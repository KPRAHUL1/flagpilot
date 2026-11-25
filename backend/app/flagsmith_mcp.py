from __future__ import annotations

from typing import Any
from .config import Settings


class FlagsmithMCPClient:
    """Connects to the remote Flagsmith MCP Server via Streamable HTTP."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.flagsmith_org_api_key.strip())

    def _headers(self) -> dict[str, str]:
        token = self.settings.flagsmith_org_api_key.strip()
        if not token.lower().startswith("api-key "):
            token = f"Api-Key {token}"
        return {"Authorization": token}

    async def _open_and_run(self, callback):
        import httpx
        from mcp import ClientSession
        from mcp.client import streamable_http

        # Handle both mcp 1.x (streamablehttp_client) and newer (streamable_http_client)
        headers = self._headers()
        if hasattr(streamable_http, "streamable_http_client"):
            async with httpx.AsyncClient(headers=headers, timeout=20.0) as http_client:
                async with streamable_http.streamable_http_client(
                    self.settings.flagsmith_mcp_url,
                    http_client=http_client,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        return await callback(session)

        async with streamable_http.streamablehttp_client(
            self.settings.flagsmith_mcp_url,
            headers=headers,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await callback(session)

    async def list_tools(self) -> dict[str, Any]:
        if not self.is_configured:
            return {"connected": False, "tools": [], "reason": "FLAGSMITH_ORG_API_KEY not set"}
        try:
            async def _run(session):
                resp = await session.list_tools()
                return [
                    {"name": t.name, "description": (t.description or "")[:140]}
                    for t in resp.tools
                ]

            tools = await self._open_and_run(_run)
            return {"connected": True, "tools": tools}
        except Exception as exc:  # noqa: BLE001
            return {"connected": False, "tools": [], "reason": str(exc)}

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "FLAGSMITH_ORG_API_KEY not set"}
        try:
            async def _run(session):
                result = await session.call_tool(tool_name, arguments=arguments)
                texts = []
                for block in getattr(result, "content", []) or []:
                    text = getattr(block, "text", None)
                    if text:
                        texts.append(text)
                return {
                    "ok": not getattr(result, "isError", False),
                    "tool": tool_name,
                    "content": "\n".join(texts),
                }

            return await self._open_and_run(_run)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "tool": tool_name, "error": str(exc)}
