"""Client for the Nemotron NIM (OpenAI-compatible API) + offline fake.

We talk to the NIM with plain `httpx` — no `openai` dependency. The NIM exposes
the well-known `/v1/chat/completions` shape, so a request is just a POST of
{model, messages, tools}; the response is text or `tool_calls`.

Tools never construct a client directly — they call `get_nim_client()`, which
returns the real client on the Spark or a `FakeNIMClient` when `nim_offline` is
set (laptop dev/demo). Tests should monkeypatch `get_nim_client` to inject a mock.
"""

from __future__ import annotations

import httpx


class NIMClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """One chat-completions round trip. Returns the raw JSON response."""
        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload)
            resp.raise_for_status()
            return resp.json()


class FakeNIMClient:
    """Offline stand-in for the NIM — returns a deterministic canned completion so
    the app runs end-to-end with no model.

    Returns the same OpenAI response shape as `NIMClient.chat`. Narration tools can
    use the placeholder prose directly; structured tools (parse_goal,
    propose_candidates) will not find parseable JSON here and should fall back to
    their defaults. For real assertions, tests mock the client instead.
    """

    def __init__(self, model: str = "fake-nim") -> None:
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        content = (
            "[offline] Model unavailable; this is placeholder narration generated "
            "from the provided metrics without a live model."
        )
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def get_nim_client() -> "NIMClient | FakeNIMClient":
    """Return the model client. Override/monkeypatch this in tests.

    Returns a `FakeNIMClient` when `settings.nim_offline` is True (laptop), else the
    real `NIMClient` pointed at the Nemotron NIM (Spark).
    """
    from app.config import get_settings

    s = get_settings()
    if s.nim_offline:
        return FakeNIMClient(s.nim_model)
    return NIMClient(s.nim_base_url, s.nim_model)
