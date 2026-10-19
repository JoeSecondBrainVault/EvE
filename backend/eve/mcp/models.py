"""Data models for Model Context Protocol (MCP) clients and servers."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    description: str = ""


class MCPTool(BaseModel):
    server_name: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallResult(BaseModel):
    tool_name: str
    content: list[dict[str, Any]] = Field(default_factory=list)
    is_error: bool = False
    raw_response: dict[str, Any] = Field(default_factory=dict)
