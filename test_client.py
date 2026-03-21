import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import sys
import logging

# We just want to catch the standard logging messages that the MCP client processes internally
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

async def main():
    params = StdioServerParameters(
        command="python",
        args=["D:\\DEV\\mcp\\universai\\orchestra\\Agent_notify\\server.py"],
    )
    
    print("Starting agent-notify client test sequence...")
    print("We will call get_notifications and intercept ctx.info (logging) events from the server.\\n")
    
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            print("Initializing session...")
            await session.initialize()
            
            # FastMCP uses the standard MCP "notifications/message" internally for ctx.info().
            # Depending on the Python SDK version, there is `session.on_notification()`,
            # or `session._notification_handlers`. 
            # We'll just hook into standard notifications using the built-in dictionary map if it exists.
            
            if hasattr(session, "_notification_handlers"):
                async def handle_notification(msg):
                    try:
                        data = dict(msg)["params"]["data"]
                        parsed = json.loads(data)
                        print(f"\\n✅ REALTIME NOTIFICATION RECEIVED:")
                        print(json.dumps(parsed, indent=2))
                    except Exception as e:
                        print(f"\\n🔔 RAW MSG: {msg}")
                session._notification_handlers["notifications/message"] = handle_notification
            
            print("\\nCalling get_notifications (streaming forever)...")
            try:
                # This tool call doesn't return normally until canceled
                await asyncio.wait_for(
                    session.call_tool("get_notifications"),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                print("\\nTest finished (30s timeout). The test client successfully listened for 30s.")
            except Exception as e:
                print(f"Tool call threw exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
