"""Model Context Protocol (MCP) Client Module for E.V.E."""

from __future__ import annotations

from eve.mcp.client import MCPClient
from eve.mcp.manager import MCPManager
from eve.mcp.models import MCPServerConfig, MCPTool

__all__ = ["MCPClient", "MCPManager", "MCPServerConfig", "MCPTool"]
