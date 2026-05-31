"""Live smoke test for a Nemotron NIM — does the real model do tool-calling the way
our agent loop (app/routers/chat.py) expects?

The unit tests only exercise the loop against a scripted fake. This script talks to
a REAL NIM endpoint and checks the one thing the fake can't: that the model, given an
OpenAI-style tool schema, actually returns a `tool_calls` array with a function name
and JSON `arguments` string we can parse.

Usage (once a NIM is serving an OpenAI-compatible /v1 API):
    TRANSITRL_NIM_BASE_URL=http://localhost:8001/v1 \
    TRANSITRL_NIM_MODEL=<model-id> \
    .venv/bin/python scripts/nim_smoke_test.py

Exit code 0 = the model emitted a well-formed tool call we can dispatch.
"""

from __future__ import annotations

import json
import os
import sys

import httpx

BASE_URL = os.environ.get("TRANSITRL_NIM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
MODEL = os.environ.get("TRANSITRL_NIM_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")

# A deliberately tool-shaped prompt + a single simple tool. If the model is
# tool-calling-capable it should choose to call this rather than answer in prose.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_upcoming_events",
            "description": "Find upcoming Toronto events (festivals, closures) in a date window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {"type": "string", "description": "ISO date, e.g. 2026-06-01"},
                    "days_ahead": {"type": "integer"},
                },
                "required": ["as_of", "days_ahead"],
            },
        },
    }
]
MESSAGES = [
    {"role": "system", "content": "You are a Toronto transit copilot. Use tools to get facts."},
    {"role": "user", "content": "What major events are coming up in the next 60 days from June 1 2026?"},
]


def main() -> int:
    print(f"→ NIM: {BASE_URL}  model: {MODEL}")
    try:
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            json={"model": MODEL, "messages": MESSAGES, "tools": TOOLS},
            timeout=120.0,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — smoke test: any failure is a clear red
        print(f"✗ could not reach / call the NIM: {exc}")
        return 1

    data = resp.json()
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError):
        print(f"✗ unexpected response shape:\n{json.dumps(data, indent=2)[:800]}")
        return 1

    tool_calls = msg.get("tool_calls")
    if not tool_calls:
        print("✗ model answered in prose, no tool_calls — tool-calling may be unsupported.")
        print(f"  content: {(msg.get('content') or '')[:300]}")
        return 1

    tc = tool_calls[0]
    name = tc.get("function", {}).get("name")
    raw_args = tc.get("function", {}).get("arguments")
    print(f"✓ tool_calls present: {name}({raw_args})")
    try:
        parsed = json.loads(raw_args or "{}")
    except json.JSONDecodeError as exc:
        print(f"✗ arguments are not valid JSON ({exc}) — loop's json.loads would fail.")
        return 1
    print(f"✓ arguments parse as JSON: {parsed}")
    print("✓ SMOKE TEST PASSED — the model's tool-calling matches what the loop expects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
