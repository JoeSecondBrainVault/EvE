"""MCP Server Manager: loads server configurations, orchestrates connections, and routes tool calls."""

from __future__ import annotations

import json
import logging
from typing import Any

from eve.config import Settings, get_settings
from eve.mcp.client import MCPClient
from eve.mcp.models import MCPServerConfig, MCPTool, MCPToolCallResult

logger = logging.getLogger(__name__)


class MCPManager:
    """Manages active MCP servers, tools, and execution routing."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._clients: dict[str, MCPClient] = {}
        self.config_file = self.settings.data_dir / "mcp_servers.json"
        self._ensure_default_config()

    def _ensure_default_config(self) -> None:
        """Creates a sample mcp_servers.json if none exists."""
        if not self.config_file.exists():
            import sys

            default_config = {
                "servers": [
                    {
                        "name": "google_workspace",
                        "command": sys.executable,
                        "args": ["-m", "eve.mcp.servers.workspace"],
                        "enabled": False,
                        "description": "Google Classroom, Gmail, Calendar MCP tools",
                    }
                ]
            }
            try:
                self.config_file.parent.mkdir(parents=True, exist_ok=True)
                self.config_file.write_text(json.dumps(default_config, indent=2), encoding="utf-8")
            except Exception as exc:
                logger.debug("Could not write default mcp_servers.json: %s", exc)

    def load_servers(self) -> None:
        """Reads configuration and connects to all enabled MCP servers."""
        if not self.config_file.exists():
            return

        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            servers_raw = data.get("servers", [])
            for s_cfg in servers_raw:
                cfg = MCPServerConfig(**s_cfg)
                if cfg.enabled and cfg.name not in self._clients:
                    client = MCPClient(cfg)
                    if client.connect():
                        self._clients[cfg.name] = client
        except Exception as exc:
            logger.error("Failed to load MCP servers from %s: %s", self.config_file, exc)

    def list_all_tools(self) -> list[MCPTool]:
        """Returns all tools across all active MCP servers."""
        all_tools: list[MCPTool] = []
        for client in self._clients.values():
            if client.is_connected:
                all_tools.extend(client.list_tools())
        return all_tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolCallResult:
        """Finds the server providing tool_name and dispatches the execution."""
        for client in self._clients.values():
            if not client.is_connected:
                continue
            for t in client.list_tools():
                if t.name == tool_name:
                    return client.call_tool(tool_name, arguments)

        return MCPToolCallResult(
            tool_name=tool_name,
            is_error=True,
            content=[{"type": "text", "text": f"Tool '{tool_name}' not found on any connected MCP server."}],
        )

    def list_servers(self) -> list[dict[str, Any]]:
        """Returns all configured servers with their running status and discovered tools."""
        if not self.config_file.exists():
            return []
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            servers = data.get("servers", [])
            results = []
            for s in servers:
                name = s.get("name", "")
                client = self._clients.get(name)
                is_connected = client.is_connected if client else False
                tools = [t.model_dump() for t in client.list_tools()] if (client and is_connected) else []
                results.append({
                    **s,
                    "connected": is_connected,
                    "tools": tools,
                })
            return results
        except Exception as exc:
            logger.error("Failed to list servers: %s", exc)
            return []

    def save_server(self, config: MCPServerConfig) -> bool:
        """Adds or updates an MCP server configuration and synchronizes connection state."""
        try:
            data = {"servers": []}
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
            servers = data.get("servers", [])
            updated = False
            for i, s in enumerate(servers):
                if s.get("name") == config.name:
                    servers[i] = config.model_dump()
                    updated = True
                    break
            if not updated:
                servers.append(config.model_dump())
            data["servers"] = servers
            self.config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

            # Update client runtime connection
            if config.name in self._clients:
                self._clients[config.name].disconnect()
                del self._clients[config.name]
            if config.enabled:
                client = MCPClient(config)
                if client.connect():
                    self._clients[config.name] = client
                else:
                    logger.warning("Failed to connect to MCP server '%s'", config.name)
                    return False
            return True
        except Exception as exc:
            logger.error("Failed to save server config: %s", exc)
            return False

    def shutdown(self) -> None:
        """Disconnects all running MCP clients."""
        for client in self._clients.values():
            client.disconnect()
        self._clients.clear()

