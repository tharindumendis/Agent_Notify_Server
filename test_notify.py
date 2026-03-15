"""
test_notify.py — Standalone notification test
---------------------------------------------
Connects to Agent_notify and prints every notification received.
No input() — pure asyncio. Run this and send a Telegram message
to confirm the whole pipeline works.

Usage:
    python test_notify.py
"""

import asyncio
import json
import os
import sys

# Add Agent_head to path so we can reuse its config
sys.path.insert(0, r"D:\DEV\mcp\universai\orchestra\Agent_head")

from mcp.client.session import ClientSession as _BaseMCPSession
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client


NOTIFY_COMMAND = "python"
NOTIFY_ARGS    = [r"D:\DEV\mcp\universai\orchestra\Agent_notify\server.py"]
NOTIFY_ENV     = {
    "AGENT_NOTIFY_CONFIG": r"D:\DEV\mcp\universai\orchestra\Agent_notify\notify_config.yaml",
}

YELLOW = "\033[33m"
GREEN  = "\033[32m"
RED    = "\033[31m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


class _CapturingSession(_BaseMCPSession):
    """ClientSession subclass that prints notifications immediately."""

    notification_count = 0

    async def _received_notification(self, notification):
        # Always call parent first
        try:
            await super()._received_notification(notification)
        except Exception as e:
            print(f"{RED}[super error] {e}{RESET}", flush=True)

        method = str(getattr(notification, "method", ""))
        # ── Introspect: show full notification structure ──────────────────
        print(f"{YELLOW}[raw notification]{RESET}", flush=True)
        print(f"  type(notification)  = {type(notification)}", flush=True)
        print(f"  method              = {method!r}", flush=True)
        print(f"  dir(notification)   = {[a for a in dir(notification) if not a.startswith('__')]}", flush=True)
        if hasattr(notification, "root"):
            print(f"  notification.root   = {notification.root!r}", flush=True)
            inner = notification.root
            print(f"  type(root)          = {type(inner)}", flush=True)
            print(f"  root.method         = {getattr(inner, 'method', '???')!r}", flush=True)
            print(f"  root.params         = {getattr(inner, 'params', '???')!r}", flush=True)
        print(flush=True)

        if "message" not in method:
            return

        params_obj = getattr(notification, "params", None)
        if not params_obj:
            print(f"{RED}[no params]{RESET}", flush=True)
            return

        data = getattr(params_obj, "data", None) or str(params_obj)
        print(f"{YELLOW}[data] {str(data)[:200]}{RESET}", flush=True)

        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            _CapturingSession.notification_count += 1
            n = _CapturingSession.notification_count

            if parsed.get("type") == "started":
                print(f"\n{GREEN}[#{n}] ✅ Agent_notify started: {parsed.get('message')}{RESET}", flush=True)
            elif "change" in parsed:
                change  = parsed["change"]
                added   = change.get("added", [])
                removed = change.get("removed", [])
                label   = f"{parsed.get('server')}/{parsed.get('tool')}"
                print(f"\n{BOLD}{YELLOW}[#{n}] 🔔 CHANGE DETECTED: {label}{RESET}", flush=True)
                print(f"  +{len(added)} added, -{len(removed)} removed", flush=True)
                if added:
                    print(f"  First added: {json.dumps(added[0], ensure_ascii=False)[:300]}", flush=True)
            else:
                print(f"\n[#{n}] Notification: {json.dumps(parsed)[:300]}", flush=True)

        except Exception as pe:
            print(f"{RED}[parse error] {pe} | data={data!r}{RESET}", flush=True)


async def main():
    print(f"{BOLD}=== Agent_notify Connection Test ==={RESET}")
    print(f"Connecting to: {NOTIFY_COMMAND} {NOTIFY_ARGS}")
    print(f"Waiting for notifications (no input blocking)...")
    print(f"Send a Telegram message to trigger a change.")
    print("-" * 60, flush=True)

    env = {**os.environ, **NOTIFY_ENV}
    params = StdioServerParameters(
        command=NOTIFY_COMMAND,
        args=NOTIFY_ARGS,
        env=env,
    )

    try:
        async with stdio_client(params) as (read, write):
            print(f"{GREEN}[+] stdio connected{RESET}", flush=True)

            async with _CapturingSession(read, write) as session:
                print(f"{GREEN}[+] session created — class={type(session).__name__}{RESET}", flush=True)
                await session.initialize()
                print(f"{GREEN}[+] session initialized{RESET}", flush=True)

                print(f"\nCalling get_notifications() — will block until server stops...")
                print(f"Watching for ctx.info() events...\n", flush=True)

                result = await session.call_tool("get_notifications", {})
                print(f"\n[done] Tool returned: {result}", flush=True)

    except Exception as e:
        print(f"{RED}[ERROR] {type(e).__name__}: {e}{RESET}", flush=True)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
