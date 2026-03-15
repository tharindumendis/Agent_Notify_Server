# agent-notify

Universal MCP notification relay.

Agent_notify polls one or more MCP servers for configured tools and streams any changes as JSON notifications via MCP log events.

## Install (using `uv`)

This repository is designed to work with `uv` (a thin wrapper around `python`/`pip` used throughout this workspace).

```sh
cd Agent_notify
uv venv .venv          # creates a virtualenv in .venv
.venv\Scripts\activate  # Windows (use `source .venv/bin/activate` on macOS/Linux)
uv sync                 # install dependencies from pyproject.toml
```

## Quickstart (using `uv run`)

1. Create or edit `notify_config.yaml` (a default example is provided in the repository).
2. Run the agent:

```sh
uv run agent-notify
```

You can override the config path:

```sh
AGENT_NOTIFY_CONFIG=/path/to/notify_config.yaml uv run agent-notify
```

> If you prefer, you can still install from PyPI:
>
> ```sh
> pip install agent-notify
> agent-notify
> ```

## How it works

- Polls every configured server/tool at `poll_interval` seconds.
- When a tool's returned value changes between polls, it emits a JSON notification.
- Notifications are streamed as log events (MCP `ctx.info`) until the client disconnects.

## Usage notes

- Enable debug logging by setting `debug: true` in `notify_config.yaml`.
- Logs are written to stderr and optionally to `log_file` when configured.
