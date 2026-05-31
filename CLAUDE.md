# 11ElevenHacks

## Documentation

- [Project Idea: TransitRL](docs/project-idea.md) — what this project is and the thinking behind it.
- [Agent Tools & MCP Layer](docs/agent-tools.md) — the unified vision: how datasets map to the tools the AI agent calls via MCP, and how they compose.
- [Map Data Layer Catalog](docs/data-layer.md) — datasets for the map/data layer, by grid channel, plus what's already in `data/`.
- [Reward & Optimizer Design](docs/reward-and-optimizer.md) — how to quantify stop-placement reward from real per-cell data, and why greedy + local search (not RL).
- [Agent Orchestration Playbook](docs/agent-orchestration.md) — how to run Claude Code coding sub-agents (esp. in parallel) so they follow instructions.
- [Runtime Agent Reliability](docs/agent-reliability.md) — how the Nemotron agent reliably interprets chat, calls tools correctly, and executes workflows in order.
- [Next.js Best Practices](docs/best-practices/nextjs.md) — conventions for the Next.js frontend.
- [FastAPI Best Practices](docs/best-practices/fastapi.md) — conventions for the Python backend (runs on the Spark).
- [Testing Best Practices](docs/best-practices/testing.md) — how to write and maintain tests.

## Backend & tools

- The backend lives in `backend/` (FastAPI, runs on the Spark). See [FastAPI Best Practices](docs/best-practices/fastapi.md).
- Tools live one family per module under `backend/app/tools/` (`city_state`, `diagnostics`, `simulation`, `optimization`, `explanation`), registered with the `@tool` decorator and auto-imported by `app/tools/__init__.py`. Tests mirror this under `backend/tests/tools/test_<family>.py`. This split keeps parallel work collision-free — a contributor edits only their family module + its test file.
- The `tool-builder` agent (`.claude/agents/tool-builder.md`) implements a family end-to-end with tests.

## Agent orchestration strategies

Coding sub-agents live in `.claude/agents/` (the `tool-builder` and `view-*` builders, with a `SHARED-BRIEF.md`). To get reliable instruction-following — especially with several agents in parallel — follow the [Agent Orchestration Playbook](docs/agent-orchestration.md). The core strategies:

- **Parallelize the work, centralize the decisions.** Each agent gets a lean, isolated context; every cross-boundary decision (naming, contracts, data shapes) goes in the shared brief + a frozen interface.
- **One file, one owner; worktree + branch per agent; the lead merges** one branch at a time, running the suite after each.
- **Specs: one job, exact file scope, invariants block, positive phrasing, motivate rules; restate non-negotiables at the end.** Keep specs ~30–60 lines and CLAUDE.md short (bloat = ignored rules).
- **Close the loop:** give each agent a runnable check, require evidence before "done", protect tests from edits, and prefer deterministic hooks over advisory prose. Review the diff in a fresh context.

## Testing

- When a test run produces a lot of output, **pipe it to a file and search it** instead of scrolling the whole dump — e.g. `pytest 2>&1 | tee /tmp/t.log` then `grep -nE "FAIL|ERROR|assert" /tmp/t.log`. Much faster to find what broke.
- Run the backend suite with the venv interpreter from `backend/`: `./.venv/Scripts/python.exe -m pytest -q`. To test a single family in isolation, target its file: `... -m pytest tests/tools/test_<family>.py`.

## Committing

- When creating commits, credit only the user (Daniel). Do **not** add a `Co-Authored-By: Claude` line or any other self-attribution.
