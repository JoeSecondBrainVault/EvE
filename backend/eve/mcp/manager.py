"""MCP Server Manager: loads server configurations, orchestrates connections, and routes tool calls."""

from __future__ import annotations

import json
import logging
from typing import Any

from eve.config import Settings, get_settings
from eve.mcp.client import MCPClient
from eve.mcp.models import MCPServerConfig, MCPTool, MCPToolCallResult

logger = logging.getLogger(__name__)

DANGEROUS_ENV_PREFIXES = (
    "PYTHON",
    "LD_",
    "DYLD_",
    "PERL",
    "RUBY",
    "NODE_",
    "BASH",
    "SHELL",
)

DANGEROUS_ENV_KEYS = {
    "ENV",
    "SHELL",
    "PROMPT_COMMAND",
    "PS1",
    "IFS",
    "PATH",
    "TMPDIR",
    "TEMP",
    "TMP",
    "COMSPEC",
    "SYSTEMROOT",
    "WINDIR",
    "SSLKEYLOGFILE",
    "KRB5_CONFIG",
}


def is_safe_env_key(key: str) -> bool:
    """Checks whether an environment variable key is safe to pass to child processes."""
    if not isinstance(key, str) or not key:
        return False
    import re

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
        return False
    upper = key.upper()
    if upper in DANGEROUS_ENV_KEYS:
        return False
    if any(upper.startswith(prefix) for prefix in DANGEROUS_ENV_PREFIXES):
        return False
    return True


def validate_mcp_config(config: MCPServerConfig) -> tuple[bool, str]:
    """Strictly validates MCPServerConfig name, command, args, and env against security policy."""
    import re
    import sys
    from pathlib import Path

    # 1. Validate server name
    if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", config.name):
        return False, "Invalid server name. Must contain only alphanumeric characters, dashes, or underscores."

    # 2. Strictly validate command runtime: ONLY active Python virtualenv executable
    cmd_str = (config.command or "").strip()
    cmd_path = Path(cmd_str)
    is_allowed_cmd = False

    if len(cmd_path.parts) > 1 or cmd_path.is_absolute():
        try:
            resolved_cmd = cmd_path.resolve()
            sys_exe = Path(sys.executable).resolve()
            venv_prefix = Path(sys.prefix).resolve()
            if resolved_cmd == sys_exe or resolved_cmd.is_relative_to(venv_prefix):
                is_allowed_cmd = True
                config.command = sys.executable
        except Exception:
            is_allowed_cmd = False
    else:
        base_name = cmd_str.lower()
        if base_name in ("python", "python3", "python.exe"):
            is_allowed_cmd = True
            config.command = sys.executable

    if not is_allowed_cmd:
        return False, f"Disallowed command runtime: '{config.command}'. Only the active Python virtualenv is permitted."

    # 3. Pin args strictly to app-shipped modules in eve.mcp.servers: ["-m", "eve.mcp.servers.<module>"]
    if (
        len(config.args) != 2
        or config.args[0] != "-m"
        or not config.args[1].startswith("eve.mcp.servers.")
    ):
        return False, "Disallowed arguments. MCP servers must strictly use '-m eve.mcp.servers.<module_name>' without additional flags or script paths."

    module_name = config.args[1][len("eve.mcp.servers."):]
    if not re.match(r"^[a-zA-Z0-9_]+$", module_name):
        return False, f"Invalid module target: '{config.args[1]}'."

    server_py = Path(__file__).parent / "servers" / f"{module_name}.py"
    if not server_py.exists():
        return False, f"Unknown MCP server module: '{config.args[1]}'."

    # 4. Strictly validate env: reject any dangerous environment variable (S5 fix)
    for env_k in (config.env or {}).keys():
        if not is_safe_env_key(env_k):
            return False, f"Disallowed environment variable: '{env_k}'. Setting runtime, loader, or interpreter control variables is forbidden."

    return True, ""


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
        """Reads configuration and connects to all enabled MCP servers after validating security policy."""
        if not self.config_file.exists():
            return

        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            servers_raw = data.get("servers", [])
            for s_cfg in servers_raw:
                try:
                    cfg = MCPServerConfig(**s_cfg)
                    valid, err_msg = validate_mcp_config(cfg)
                    if not valid:
                        logger.warning("Skipping invalid/untrusted MCP server '%s' from config: %s", cfg.name, err_msg)
                        continue
                    if cfg.enabled and cfg.name not in self._clients:
                        client = MCPClient(cfg)
                        if client.connect():
                            self._clients[cfg.name] = client
                except Exception as inner_exc:
                    logger.warning("Error parsing server config entry %s: %s", s_cfg, inner_exc)
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
        valid, err_msg = validate_mcp_config(config)
        if not valid:
            logger.warning("Rejected invalid MCP server config '%s': %s", config.name, err_msg)
            return False

        try:
            # 1. If enabling, verify connection first before persisting to disk (N18 fix)
            new_client: MCPClient | None = None
            if config.enabled:
                new_client = MCPClient(config)
                if not new_client.connect():
                    logger.warning("Failed to connect to MCP server '%s'", config.name)
                    return False

            # 2. Connection verified or server disabled: update runtime client
            if config.name in self._clients:
                self._clients[config.name].disconnect()
                del self._clients[config.name]

            if new_client is not None:
                self._clients[config.name] = new_client

            # 3. Persist valid configuration to disk only after successful verification
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
            return True
        except Exception as exc:
            logger.error("Failed to save server config: %s", exc)
            return False

    def shutdown(self) -> None:
        """Disconnects all running MCP clients."""
        for client in self._clients.values():
            client.disconnect()
        self._clients.clear()

