"""
core/config_loader.py
----------------------
Loads and validates notify_config.yaml into typed dataclasses.
Import and use `load_config()` anywhere in the project.

Config resolution priority
---------------------------
1. Explicit `path` argument passed in code
2. AGENT_NOTIFY_CONFIG environment variable
3. OS user-config dir  (created from bundled default on first run)
       Windows : %LOCALAPPDATA%\\agent-notify\\notify_config.yaml
       macOS   : ~/Library/Application Support/agent-notify/notify_config.yaml
       Linux   : $XDG_CONFIG_HOME/agent-notify/notify_config.yaml  (~/.config/…)
4. <cwd>/notify_config.yaml
5. Bundled package default  (Agent_notify/notify_config.yaml next to server.py)

On first run (priority-3 path missing) the bundled default is copied there
so users can easily edit it without touching the package installation.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# OS-specific paths
# ---------------------------------------------------------------------------


def get_app_config_dir() -> Path:
    """
    Returns the OS-specific user-editable config directory for agent-notify.

    - Windows : %LOCALAPPDATA%\\agent-notify
    - macOS   : ~/Library/Application Support/agent-notify
    - Linux   : $XDG_CONFIG_HOME/agent-notify  (default ~/.config/agent-notify)
    """
    if os.name == "nt":  # Windows
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":  # macOS
        base = Path.home() / "Library" / "Application Support"
    else:  # Linux / other POSIX
        base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))

    config_dir = base / "agent-notify"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


# ---------------------------------------------------------------------------
# Bootstrap — copy bundled default config to OS user-config dir on first run
# ---------------------------------------------------------------------------

# The bundled default sits next to server.py (package root)
_PACKAGE_DEFAULT_CONFIG = Path(__file__).parent.parent / "notify_config.yaml"


def bootstrap_config() -> Path:
    """
    Ensures a user-editable notify_config.yaml exists in the OS config directory.

    - If it already exists  → does nothing, returns the existing path.
    - If it doesn't exist   → copies the bundled default there and logs a
                               message so the user knows where to find it.

    Returns the path to the user config file (whether new or pre-existing).
    """
    user_config = get_app_config_dir() / "notify_config.yaml"

    if user_config.exists():
        return user_config

    # First run — copy the bundled default
    if _PACKAGE_DEFAULT_CONFIG.exists():
        shutil.copy2(_PACKAGE_DEFAULT_CONFIG, user_config)
        logger.info(
            "[agent-notify] First-run bootstrap: config copied to %s\n"
            "               Edit that file to customise your notify server settings.",
            user_config,
        )
    else:
        logger.warning(
            "[agent-notify] Bundled default config not found at %s; "
            "skipping bootstrap. User config path: %s",
            _PACKAGE_DEFAULT_CONFIG,
            user_config,
        )

    return user_config


def load_config(path: str | None = None) -> NotifyConfig:
    """
    Load the notify server config.  Resolution priority:

    1. ``path``  — explicit path passed by the caller
    2. ``AGENT_NOTIFY_CONFIG``   — environment variable
    3. OS user-config   — bootstrapped on first run from the bundled default
       ``%LOCALAPPDATA%\\agent-notify\\notify_config.yaml``  (Windows)
       ``~/Library/Application Support/agent-notify/notify_config.yaml``  (macOS)
       ``~/.config/agent-notify/notify_config.yaml``  (Linux)
    4. ``<cwd>/notify_config.yaml``           — dev / monorepo convenience
    5. ``<package_root>/notify_config.yaml``  — bundled package fallback
    """
    env_path = os.getenv("AGENT_NOTIFY_CONFIG")
    user_config_path = bootstrap_config()
    cwd_path = Path.cwd() / "notify_config.yaml"
    package_root_path = _PACKAGE_DEFAULT_CONFIG

    if path:
        final_path = Path(path)
    elif env_path:
        final_path = Path(env_path)
    elif user_config_path.exists():
        final_path = user_config_path
    elif cwd_path.exists():
        final_path = cwd_path
    else:
        final_path = package_root_path

    if not final_path.exists():
        raise FileNotFoundError(
            f"Config file not found. Checked:\n"
            f"  1. Explicit path              : {path}\n"
            f"  2. Env var AGENT_NOTIFY_CONFIG: {env_path}\n"
            f"  3. OS user-config              : {user_config_path}\n"
            f"  4. CWD                         : {cwd_path}\n"
            f"  5. Package default             : {package_root_path}\n"
            f"Please ensure a 'notify_config.yaml' exists at one of the above locations."
        )

    logger.info("[agent-notify] Using config: %s", final_path.resolve())

    with open(final_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Resolve relative paths in the config relative to the config file's own
    # directory, not the CWD — avoids surprises when launched from different dirs.
    config_dir = final_path.resolve().parent

    def resolve_path(p: str) -> str:
        """Make a relative path absolute, anchored to the config file's dir."""
        path_obj = Path(p).expanduser()
        if not path_obj.is_absolute():
            path_obj = (config_dir / path_obj).resolve()
        return str(path_obj)

    # Resolve log_file relative to config file if it's relative
    log_file_raw = data.get("log_file", None)
    if log_file_raw:
        log_file = resolve_path(log_file_raw)
    else:
        log_file = None

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
        log_file=log_file,
    )
