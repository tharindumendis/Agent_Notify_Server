"""
core/poller.py
--------------
Connects to all configured MCP servers as a CLIENT, then polls each
server's configured tools on every tick, diffing results to detect changes.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from core.config_loader import NotifyConfig
from core.differ import diff_results


class Poller:
    """
    Manages persistent MCP client connections to all configured servers
    and polls their tools on each call to poll_all().
    """

    def __init__(self, config: NotifyConfig) -> None:
        self.config = config
        self._sessions: dict[str, ClientSession] = {}
        self._last_results: dict[str, str | None] = {}
        self._stack = AsyncExitStack()

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "Poller":
        await self._stack.__aenter__()
        for server in self.config.servers:
            try:
                env = {**os.environ, **server.env}
                params = StdioServerParameters(
                    command=server.command,
                    args=server.args,
                    env=env,
                )
                transport = await self._stack.enter_async_context(
                    stdio_client(params)
                )
                read, write = transport
                session = await self._stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()
                self._sessions[server.name] = session
            except Exception as exc:
                # Partial failure — log to stderr, continue with other servers
                import sys
                print(
                    f"[agent-notify] WARNING: could not connect to '{server.name}': {exc}",
                    file=sys.stderr,
                )
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._stack.__aexit__(*args)

    # ── Polling ───────────────────────────────────────────────────────────────

    async def poll_all(self, first_poll: bool = False) -> list[dict]:
        """
        Call every configured tool on every connected server.
        Compare results to the previous poll and return a list of change events.

        On *first_poll* we only baseline the results (no changes emitted).
        """
        events: list[dict] = []

        for server in self.config.servers:
            session = self._sessions.get(server.name)
            if session is None:
                continue

            for tool_cfg in server.tools:
                key = f"{server.name}::{tool_cfg.name}"

                try:
                    result = await asyncio.wait_for(
                        session.call_tool(tool_cfg.name, arguments=tool_cfg.args),
                        timeout=30.0,
                    )
                    
                    import sys
                    print(f"[DEBUG] Outcome of '{tool_cfg.name}' on '{server.name}': {result}", file=sys.stderr)

                    # Extract the text payload from the MCP result
                    new_data: str | None = None
                    for content in result.content or []:
                        if hasattr(content, "text") and content.text:
                            new_data = content.text
                            break

                    old_data = self._last_results.get(key)
                    self._last_results[key] = new_data

                    # First poll: baseline only — emit nothing
                    if first_poll:
                        continue

                    # Skip if we have nothing to compare yet
                    if old_data is None or new_data is None:
                        continue

                    change = diff_results(old_data, new_data)
                    if change:
                        events.append({
                            "server": server.name,
                            "tool":   tool_cfg.name,
                            "change": change,
                        })

                except asyncio.TimeoutError:
                    if not first_poll:
                        events.append({
                            "server": server.name,
                            "tool":   tool_cfg.name,
                            "error":  "Tool call timed out (30 s)",
                        })

                except Exception as exc:
                    if not first_poll:
                        events.append({
                            "server": server.name,
                            "tool":   tool_cfg.name,
                            "error":  str(exc),
                        })

        return events
