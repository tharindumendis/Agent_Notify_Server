"""
server.py — Agent_notify MCP Server
--------------------------------------
A FastMCP server that exposes a single long-running tool: get_notifications().

When called, it:
  1. Connects to all MCP servers listed in notify_config.yaml
  2. Polls configured tools at poll_interval seconds
  3. Diffs each result against the previous poll
  4. Sends every change as a ctx.info(json) log notification WITHOUT
     closing the tool call — the client receives a stream of events

Debug mode (debug: true in notify_config.yaml):
  - Logs every poll cycle to the configured log_file
  - Format: timestamped lines with server/tool/status/changes

Usage:
    agent-notify                          # uses notify_config.yaml in cwd
    AGENT_NOTIFY_CONFIG=/path/to/cfg.yaml agent-notify
    uvx agent-notify
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Context

from core.config_loader import NotifyConfig, load_config
from core.poller import Poller

mcp = FastMCP(
    "agent-notify",
    instructions=(
        "Universal MCP notification relay. "
        "Call get_notifications() to subscribe to real-time change events "
        "from all configured MCP servers. "
        "Events are streamed as log notifications (ctx.info) — "
        "the tool call does not return until the client disconnects."
    ),
)


# ---------------------------------------------------------------------------
# Debug logger
# ---------------------------------------------------------------------------

def _make_logger(config: NotifyConfig) -> logging.Logger:
    """Set up a file logger when debug=true, else a null logger."""
    log = logging.getLogger("agent_notify")
    log.setLevel(logging.DEBUG if config.debug else logging.WARNING)
    log.handlers.clear()

    if config.debug:
        fmt = logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")

        # Always write to stderr
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        log.addHandler(sh)

        # Optionally also write to a file
        if config.log_file:
            log_path = Path(config.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setFormatter(fmt)
            log.addHandler(fh)

    return log


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_notifications(ctx: Context) -> str:
    """
    Subscribe to real-time change notifications from configured MCP servers.

    This tool NEVER returns normally — it streams JSON change events as
    log notifications (ctx.info) until the client disconnects or cancels.

    Each notification is a JSON object:
        {
          "server": "<server_name>",
          "tool":   "<tool_name>",
          "change": {
            "added":   [...],   // new items in a list result
            "removed": [...],   // removed items
            // OR
            "changed": { "from": ..., "to": ... }
          }
        }

    On error polling a tool:
        { "server": "...", "tool": "...", "error": "reason" }
    """
    # Load config fresh on each call (supports hot-reload)
    try:
        config = load_config()
    except FileNotFoundError as exc:
        await ctx.error(str(exc))
        return f"ERROR: {exc}"

    log = _make_logger(config)

    n_servers = len(config.servers)
    n_tools   = sum(len(s.tools) for s in config.servers)

    log.info("Agent Notify starting | servers=%d tools=%d interval=%ds debug=%s log=%s",
             n_servers, n_tools, config.poll_interval, config.debug, config.log_file or "stderr")

    started_msg = {
        "type":             "started",
        "servers":          n_servers,
        "tools":            n_tools,
        "interval_seconds": config.poll_interval,
        "debug":            config.debug,
        "log_file":         config.log_file,
        "message": (
            f"Agent Notify: monitoring {n_tools} tool(s) across "
            f"{n_servers} server(s) every {config.poll_interval}s"
        ),
    }
    await ctx.info(json.dumps(started_msg))

    try:
        async with Poller(config) as poller:
            cycle = 0
            first = True

            while True:
                cycle += 1
                cycle_start = datetime.now()

                log.debug("── Poll cycle #%d started at %s", cycle, cycle_start.strftime("%H:%M:%S"))

                try:
                    events = await poller.poll_all(first_poll=first)
                    first = False

                    cycle_ms = int((datetime.now() - cycle_start).total_seconds() * 1000)

                    if config.debug:
                        # Log summary for every server/tool polled
                        for server in config.servers:
                            for tool_cfg in server.tools:
                                key = f"{server.name}/{tool_cfg.name}"
                                # Find matching event if any
                                match = next(
                                    (e for e in events
                                     if e.get("server") == server.name
                                     and e.get("tool") == tool_cfg.name),
                                    None
                                )
                                if match and "error" in match:
                                    log.warning("  [%s] ERROR: %s", key, match["error"])
                                elif match:
                                    change = match.get("change", {})
                                    added   = len(change.get("added", []))
                                    removed = len(change.get("removed", []))
                                    log.debug("  [%s] CHANGED | +%d -%d items", key, added, removed)
                                else:
                                    log.debug("  [%s] no change", key)

                        log.debug("── Cycle #%d done in %dms | %d change(s)",
                                  cycle, cycle_ms, len(events))

                    # Emit events to client
                    for event in events:
                        log.info("NOTIFY → %s", json.dumps(event))
                        await ctx.info(json.dumps(event))

                except Exception as poll_exc:
                    log.error("Poll cycle #%d failed: %s", cycle, poll_exc, exc_info=True)
                    await ctx.warning(json.dumps({
                        "type":  "poll_cycle_error",
                        "cycle": cycle,
                        "error": str(poll_exc),
                    }))

                log.debug("Sleeping %ds until cycle #%d …", config.poll_interval, cycle + 1)
                await asyncio.sleep(config.poll_interval)

    except asyncio.CancelledError:
        log.info("Agent Notify: subscription cancelled by client.")

    return "Agent Notify: subscription ended."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for `agent-notify` CLI command."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
