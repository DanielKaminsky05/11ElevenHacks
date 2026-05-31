"""Tests for the agent loop behind POST /chat.

The loop is driven entirely offline by a `ScriptedFakeNIMClient` — no model — so
we assert the full diagnose→answer pipeline deterministically.

Coverage:
  1. Happy path     — one tool call → final answer, with the step trace returned
  2. Tool results   — the loop feeds each tool's result back to the next turn
  3. Multi-tool     — several tool calls across turns accumulate in order
  4. Max iterations — a model that never stops calling tools is cut off
  5. Unknown tool   — surfaced as a tool result, not a crash
  6. Bad arguments  — validation error surfaced as a tool result, loop continues
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.agent.nim_client import ScriptedFakeNIMClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _patch_nim(monkeypatch, script):
    """Point the chat router at a scripted offline NIM and return it for assertions."""
    fake = ScriptedFakeNIMClient(script)
    monkeypatch.setattr("app.routers.chat.get_nim_client", lambda: fake)
    return fake


# A real, self-contained tool: find_upcoming_events needs no data dir or model.
EVENTS_ARGS = {"as_of": "2026-06-01", "days_ahead": 60}


# 1. Happy path -------------------------------------------------------------
def test_one_tool_then_answer(client, monkeypatch):
    _patch_nim(
        monkeypatch,
        script=[
            [("find_upcoming_events", EVENTS_ARGS)],
            "There are major events this summer; plan extra capacity.",
        ],
    )
    resp = client.post("/chat", json={"message": "What's happening this summer?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "There are major events this summer; plan extra capacity."
    assert len(body["steps"]) == 1
    step = body["steps"][0]
    assert step["tool"] == "find_upcoming_events"
    assert step["arguments"] == EVENTS_ARGS
    assert step["result"]["count"] > 0  # the tool actually ran


# 2. Tool results are fed back to the model ---------------------------------
def test_tool_result_fed_back(client, monkeypatch):
    fake = _patch_nim(
        monkeypatch,
        script=[
            [("find_upcoming_events", EVENTS_ARGS)],
            "done",
        ],
    )
    client.post("/chat", json={"message": "events?"})
    # The second turn's messages must include a tool message carrying the result.
    second_turn = fake.calls[1]
    tool_msgs = [m for m in second_turn if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    payload = json.loads(tool_msgs[0]["content"])
    assert payload["count"] > 0
    assert tool_msgs[0]["name"] == "find_upcoming_events"


# 3. Multiple tool calls accumulate in order --------------------------------
def test_multiple_tools_accumulate(client, monkeypatch):
    _patch_nim(
        monkeypatch,
        script=[
            [("find_upcoming_events", EVENTS_ARGS)],
            [("get_event", {"event_id": "wc-2026-06-12"})],
            "Two lookups done.",
        ],
    )
    body = client.post("/chat", json={"message": "details?"}).json()
    assert body["reply"] == "Two lookups done."
    assert [s["tool"] for s in body["steps"]] == [
        "find_upcoming_events",
        "get_event",
    ]


# 4. Runaway loop is cut off ------------------------------------------------
def test_max_iterations_guard(client, monkeypatch):
    from app.routers.chat import MAX_ITERATIONS

    # A model that always asks for another tool, more times than the guard allows.
    _patch_nim(
        monkeypatch,
        script=[[("find_upcoming_events", EVENTS_ARGS)]] * (MAX_ITERATIONS + 2),
    )
    body = client.post("/chat", json={"message": "loop forever"}).json()
    assert "tool-call limit" in body["reply"]
    assert len(body["steps"]) == MAX_ITERATIONS


# 5. Unknown tool is surfaced, not fatal ------------------------------------
def test_unknown_tool_surfaced(client, monkeypatch):
    _patch_nim(
        monkeypatch,
        script=[
            [("no_such_tool", {})],
            "I could not find that capability.",
        ],
    )
    body = client.post("/chat", json={"message": "do impossible thing"}).json()
    assert body["reply"] == "I could not find that capability."
    assert body["steps"][0]["result"]["error"].startswith("unknown tool")


# 6. Bad arguments surfaced as a recoverable tool result --------------------
def test_invalid_arguments_surfaced(client, monkeypatch):
    _patch_nim(
        monkeypatch,
        script=[
            [("find_upcoming_events", {"days_ahead": "not-a-number"})],
            "Let me try that differently.",
        ],
    )
    body = client.post("/chat", json={"message": "events?"}).json()
    assert body["reply"] == "Let me try that differently."
    assert body["steps"][0]["result"]["error"] == "invalid arguments"
