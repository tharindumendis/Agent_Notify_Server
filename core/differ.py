"""
core/differ.py
--------------
Compares old vs new MCP tool responses and returns a change summary,
or None if nothing changed.

Handles:
  - JSON arrays  → finds added / removed items by stable ID
  - JSON objects → reports key-level diff
  - scalars      → reports old vs new value
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_id(item: Any) -> str:
    """Extract or derive a stable string ID from an item."""
    if isinstance(item, dict):
        for key in ("id", "message_id", "msgId", "uid", "number",
                    "pr_number", "sha", "iid", "key", "name"):
            if key in item:
                return str(item[key])
    return hashlib.md5(
        json.dumps(item, sort_keys=True, default=str).encode()
    ).hexdigest()


def diff_results(old_raw: str | None, new_raw: str | None) -> dict | None:
    """
    Compare *old_raw* and *new_raw* (JSON strings from MCP tool responses).

    Returns a change dict, or None if there is no meaningful change.

    Change dict shape:
        { "added": [...] }          – new list items
        { "removed": [...] }        – removed list items
        { "added": [...], "removed": [...] }
        { "changed": {"from": ..., "to": ...} }  – scalar / dict change
    """
    if old_raw == new_raw:
        return None

    try:
        old = json.loads(old_raw) if isinstance(old_raw, str) else old_raw
        new = json.loads(new_raw) if isinstance(new_raw, str) else new_raw

        # ── List diff ─────────────────────────────────────────────────────────
        if isinstance(old, list) and isinstance(new, list):
            old_map = {_stable_id(i): i for i in old}
            new_map = {_stable_id(i): i for i in new}

            added   = [i for k, i in new_map.items() if k not in old_map]
            removed = [i for k, i in old_map.items() if k not in new_map]

            changes: dict = {}
            if added:
                changes["added"] = added
            if removed:
                changes["removed"] = removed
            return changes or None

        # ── Dict diff  ────────────────────────────────────────────────────────
        if isinstance(old, dict) and isinstance(new, dict):
            all_keys = set(old) | set(new)
            changed_keys = {k for k in all_keys if old.get(k) != new.get(k)}
            if not changed_keys:
                return None
            return {
                "changed": {
                    k: {"from": old.get(k), "to": new.get(k)}
                    for k in changed_keys
                }
            }

        # ── Scalar  ───────────────────────────────────────────────────────────
        if old != new:
            return {"changed": {"from": old, "to": new}}

        return None

    except (json.JSONDecodeError, TypeError):
        if old_raw != new_raw:
            return {"changed": {"from": old_raw, "to": new_raw}}
        return None
