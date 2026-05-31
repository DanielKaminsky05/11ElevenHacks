"""Live agent tool-selection + grounding eval (agent-reliability.md §5.1-5.2).

Fires a battery of golden questions at a RUNNING backend's POST /chat and reports,
per question, which tool the model actually chose vs. the expected one, plus whether
the answer was grounded in a tool result. This is the real test of the scaffolding in
docs/agent-reliability.md — the offline unit tests can't measure tool *selection*
(the fake is scripted); only a live model can.

Run it once the NIM is serving and the backend is up (TRANSITRL_NIM_OFFLINE=false):
    .venv/bin/python scripts/agent_evals.py --url http://localhost:9000 --repeats 3

--repeats k reports pass^k (the fraction of questions that pass on ALL k runs) — §5.1
notes agents are inconsistent across runs, so best-case accuracy overstates reliability.
"""

from __future__ import annotations

import argparse
import sys

import httpx

# (question, expected_tool | None for no-tool, note). Paraphrases + the confusion pair.
BATTERY = [
    ("What's the population of the Annex?", "profile_area", "fact lookup"),
    ("How many people live in Scarborough Village?", "profile_area", "paraphrase"),
    ("Tell me about the Annex.", "profile_area", "paraphrase"),
    ("Compare the population of the Annex and Rexdale.", "compare_areas", "multi-area"),
    ("What if we add three stops in Malvern?", "simulate_change", "what-if (confusion pair)"),
    ("Where should we add stops to help low-income areas?", "optimize_layout", "what-should (confusion pair)"),
    ("Which Toronto neighbourhoods are transit deserts?", "equity_gap_report", "diagnose"),
    ("Hi there!", None, "greeting -> no tool"),
    ("What can you do?", None, "capability -> no tool"),
]


def run_once(client: httpx.Client, base: str, question: str) -> tuple[list[str], str]:
    """Return (tools_called, reply) for one question."""
    resp = client.post(f"{base}/chat", json={"message": question}, timeout=180.0)
    resp.raise_for_status()
    body = resp.json()
    tools = [s["tool"] for s in body.get("steps", [])]
    return tools, body.get("reply", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:9000", help="backend base URL")
    ap.add_argument("--repeats", type=int, default=1, help="runs per question (pass^k)")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    passes = 0
    print(f"\nAgent eval — {base}  (pass^{args.repeats})\n" + "=" * 72)
    with httpx.Client() as client:
        for question, expected, note in BATTERY:
            ok_all = True
            last_tools: list[str] = []
            try:
                for _ in range(args.repeats):
                    tools, _reply = run_once(client, base, question)
                    last_tools = tools
                    chosen_ok = (expected in tools) if expected else (len(tools) == 0)
                    ok_all = ok_all and chosen_ok
            except Exception as exc:  # noqa: BLE001
                print(f"✗ ERROR  {question!r}: {exc}")
                continue
            passes += int(ok_all)
            mark = "✓" if ok_all else "✗"
            want = expected or "(no tool)"
            print(f"{mark}  want={want:16} got={','.join(last_tools) or '(none)':22} | {note}")
            print(f"     {question}")
    total = len(BATTERY)
    print("=" * 72)
    print(f"tool selection: {passes}/{total} pass^{args.repeats} ({100*passes/total:.0f}%)\n")
    return 0 if passes == total else 1


if __name__ == "__main__":
    sys.exit(main())
