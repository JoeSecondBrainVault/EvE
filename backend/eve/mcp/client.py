"""Standard I/O (stdio) Model Context Protocol (MCP) Client."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Any

from eve.mcp.models import MCPServerConfig, MCPTool, MCPToolCallResult

logger = logging.getLogger(__name__)


class MCPClient:
    """Connects to an external MCP server process via stdio JSON-RPC 2.0."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._req_id = 0
        self._tools: list[MCPTool] = []
        self._initialized = False

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.poll() is None and self._initialized

    def connect(self) -> bool:
        """Launches the MCP server subprocess and performs JSON-RPC handshake."""
        if not self.config.enabled:
            return False

        with self._lock:
            try:
                env = os.environ.copy()
                env.update(self.config.env)

                args = [self.config.command] + self.config.args
                logger.info("Spawning MCP Server '%s': %s", self.config.name, args)

                self._process = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    env=env,
                )

                # Drain stderr in background daemon thread to prevent pipe buffer deadlock
                def _drain_stderr(proc: subprocess.Popen, name: str) -> None:
                    try:
                        if proc.stderr:
                            for line in iter(proc.stderr.readline, ""):
                                if not line:
                                    break
                                logger.debug("[MCP %s stderr] %s", name, line.strip())
                    except Exception:
                        pass

                threading.Thread(
                    target=_drain_stderr,
                    args=(self._process, self.config.name),
                    name=f"mcp-stderr-{self.config.name}",
                    daemon=True,
                ).start()

                # Initialize handshake (JSON-RPC initialize)
                resp = self._send_request(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "clientInfo": {"name": "eve-assistant", "version": "0.1.0"},
                    },
                )
                if not resp or "error" in resp:
                    logger.warning("MCP server '%s' initialization error: %s", self.config.name, resp)
                    return False

                # Send initialized notification
                self._send_notification("notifications/initialized", {})

                self._initialized = True
                self._refresh_tools()
                logger.info("MCP Server '%s' connected with %d tool(s)", self.config.name, len(self._tools))
                return True
            except Exception as exc:
                logger.error("Failed to connect to MCP server '%s': %s", self.config.name, exc)
                return False

    def _refresh_tools(self) -> None:
        """Queries the server for its list of available tools."""
        res = self._send_request("tools/list", {})
        if res and "result" in res and "tools" in res["result"]:
            raw_tools = res["result"]["tools"]
            self._tools = [
                MCPTool(
                    server_name=self.config.name,
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in raw_tools
            ]

    def list_tools(self) -> list[MCPTool]:
        return list(self._tools)

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPToolCallResult:
        """Invokes a tool on this MCP server."""
        if not self.is_connected:
            raise RuntimeError(f"MCP server '{self.config.name}' is not connected.")

        resp = self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
        if not resp:
            return MCPToolCallResult(tool_name=tool_name, is_error=True, raw_response={"error": "No response"})

        if "error" in resp:
            return MCPToolCallResult(
                tool_name=tool_name,
                is_error=True,
                raw_response=resp,
                content=[{"type": "text", "text": str(resp["error"])}],
            )

        res_body = resp.get("result", {})
        return MCPToolCallResult(
            tool_name=tool_name,
            content=res_body.get("content", []),
            is_error=bool(res_body.get("isError", False)),
            raw_response=res_body,
        )

    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None

        self._req_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }

        try:
            payload = json.dumps(req) + "\n"
            self._process.stdin.write(payload)
            self._process.stdin.flush()

            line = self._process.stdout.readline()
            if not line:
                return None
            return json.loads(line)
        except Exception as exc:
            logger.error("Error communicating with MCP server '%s': %s", self.config.name, exc)
            return None

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            return

        notif = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        try:
            payload = json.dumps(notif) + "\n"
            self._process.stdin.write(payload)
            self._process.stdin.flush()
        except Exception as exc:
            logger.debug("Error sending notification to MCP server '%s': %s", self.config.name, exc)

    def disconnect(self) -> None:
        with self._lock:
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=2)
                except Exception:
                    self._process.kill()
                self._process = None
                self._initialized = False
