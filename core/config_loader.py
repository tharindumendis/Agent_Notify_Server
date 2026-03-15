"""
core/config_loader.py
----------------------
Loads and parses notify_config.yaml.

Search order for config file:
  1. AGENT_NOTIFY_CONFIG environment variable
  2. ./notify_config.yaml  (current working directory)
  3. ~/.config/agent-notify/config.yaml
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ToolPollConfig:
    """One tool to poll on a server."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ServerPollConfig:
    """One MCP server to connect to and poll."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[ToolPollConfig] = field(default_factory=list)


@dataclass
class NotifyConfig:
    poll_interval: int                        # seconds between each poll cycle
    servers: list[ServerPollConfig]
    debug: bool = False                       # log every poll cycle
    log_file: str | None = None               # path to log file (None = stderr only)


def load_config(path: str | None = None) -> NotifyConfig:
    """Load notify_config.yaml from *path* or from the default search order."""
    if path is None:
        path = os.environ.get("AGENT_NOTIFY_CONFIG")

    if path is None:
        candidates = [
            Path("notify_config.yaml"),
            Path.home() / ".config" / "agent-notify" / "config.yaml",
        ]
        for c in candidates:
            if c.exists():
                path = c
                break

    if path is None:
        raise FileNotFoundError(
            "notify_config.yaml not found. "
            "Create one in the current directory or set AGENT_NOTIFY_CONFIG."
        )

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    servers: list[ServerPollConfig] = []
    for s in data.get("servers", []):
        tools = [
            ToolPollConfig(name=t["tool"], args=t.get("args", {}))
            for t in s.get("tools", [])
        ]
        servers.append(
            ServerPollConfig(
                name=s["name"],
                command=s["command"],
                args=s.get("args", []),
                env=s.get("env", {}),
                tools=tools,
            )
        )

    return NotifyConfig(
        poll_interval=int(data.get("poll_interval", 30)),
        servers=servers,
        debug=bool(data.get("debug", False)),
        log_file=data.get("log_file", None),
    )
