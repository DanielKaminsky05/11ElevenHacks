# TransitRL — Multi-Agent Orchestration Playbook

How to run Claude Code **coding sub-agents** (the ones defined in `.claude/agents/`) so they
*actually follow instructions* — especially several in parallel. This is about the build-time
agents that write our code, not the runtime planning agent (that's
[`agent-workflows.md`](agent-workflows.md)).

> **The one idea that ties it all together:** **parallelize the work, centralize the
> decisions.** Give each agent an isolated, lean context to *do* its job, but force every
> decision that crosses an agent boundary into a single shared brief + frozen interface. Then
> gate the merge behind checks the agents can't argue with. Most "the agent ignored me"
> failures are **context failures, not model failures** — and modern Claude follows
> instructions *literally*, so vagueness, not defiance, is usually the real bug.

---

## 1. What our existing specs already get right

Before adding anything, note that [`.claude/agents/SHARED-BRIEF.md`](../.claude/agents/SHARED-BRIEF.md)
and [`tool-builder.md`](../.claude/agents/tool-builder.md) already apply most of the high-leverage
techniques. Keep doing these:

- **Strict single-file / single-module ownership** — "edit ONLY your assigned view file." Makes
  conflicts *structurally impossible* rather than resolved after the fact.
- **Git worktree + branch per agent** — physical isolation; the orchestrator merges.
- **"Orient first"** — read the spec/data/conventions before writing (tool-builder §0).
- **STOP-and-report guardrail** — "if you think a shared file needs a change, STOP and note it"
  instead of editing outside your lane.
- **Definition of done + structured final report** — list files changed, ids created, test
  status, anything blocked.
- **Self-verification** — typecheck + lint + run-your-own-tests before reporting.

This playbook generalizes those into a reusable system and adds the parts we're missing
(deterministic hooks, contract-first seams, fresh-context review).

---

## 2. The orchestration model

**Orchestrator–worker.** One lead session owns strategy: it writes the plan + shared brief,
freezes the interfaces, spawns workers (one per file/module/worktree), then verifies and merges.
Workers never coordinate peer-to-peer — everything routes through the lead.

**Parallelize work, centralize decisions** (the two primary sources agree once you split the
concerns):
- *Isolate* each worker's exploration/implementation context (lean window → better adherence).
- *Share* every cross-boundary decision (naming, error format, data shapes, libraries, layout)
  via the brief + a frozen contract — this is what prevents the classic parallel-agent failure
  where each piece is competent but they don't fit together.

**When NOT to parallelize.** If a feature is *tightly coupled* — the pieces must make consistent
micro-decisions — don't split it across agents. Split only along genuine module seams where a
written contract is the only thing that crosses. Sweet spot: **2–5 parallel agents.**

---

## 3. Writing a sub-agent spec that gets obeyed

Modern Claude follows instructions literally and is *more* responsive to the system prompt than
older models — so be precise, and don't inflate emphasis.

- **One job, stated in the first two sentences.** Narrow role = whole classes of drift removed.
- **Literal-scope pinning.** Never rely on the model to generalize from one item or infer an
  unstated request. Name exact file paths for deliverables; for unknowns, give a best-guess path
  annotated `(verify exists before modifying)` — never "the relevant controller."
- **An explicit invariants / "do not modify" block** with surgical exceptions. This is the
  highest-leverage section of a spec.
- **Positive phrasing.** "Edit only files under `app/tools/`" beats "don't touch other files."
  Negations leave the target underspecified and are routinely missed (the pink-elephant effect).
- **Motivate non-obvious rules.** A one-line *why* lets the model generalize the rule to cases
  you didn't foresee ("don't add deps — this deploys air-gapped, so anything new fails the
  build").
- **Calibrated emphasis.** Reserve `IMPORTANT` / `YOU MUST` for the few genuinely hard rules;
  on Claude 4.x, ALL-CAPS-everything causes *over*-triggering and loses signal.
- **Action-default.** Say whether the agent should implement autonomously or hold for approval —
  "suggest changes" yields prose, "change this function" yields edits.
- **Anti-overengineering clause.** Opus tends to over-deliver — "make only changes directly
  required; a bug fix doesn't need surrounding cleanup; no helpers for one-time operations."
- **Front-load the whole spec in turn one** and **restate the 2–3 non-negotiables at the very
  end** (see §4 on placement). Keep the spec tight — ~30–60 lines; longer usually means
  duplicating conventions that belong in CLAUDE.md.

A structural factorial study found instruction *content* (specificity, scope, acceptance
criteria) drives adherence far more than cosmetic file layout — so spend effort there, not on
headers.

---

## 4. Context engineering (why they drift, and the fixes)

Treat the context window as a finite **attention budget**, not storage.

- **Context rot.** Quality degrades as the window fills — *well before* the limit. Feed **paths,
  not whole files**; let the agent read what it needs; cap exploration; trim tool output at
  ingestion.
- **Lost in the middle.** Attention is U-shaped (strong at start + end, weak in the middle). Put
  hard rules + role at the **top**, reference material (code/docs) in the **middle**, and a
  one-line restatement of the deliverable + success criteria at the **end**. On conflict, the
  *later* instruction tends to win — so the closing restatement also resolves ambiguity in your
  favour.
- **Goal drift on long runs.** The agent fixates on the latest tool output and forgets the
  objective. Mitigate with a **todo list** (`TodoWrite`), a **`NOTES.md` scratchpad** for
  durable state, and periodic re-grounding ("Reminder: the goal is X; remaining: Y").
- **Keep CLAUDE.md short.** A bloated memory file is itself context rot — important rules drown.
  Bullets, categories, positive framing, build/test commands, precedence rules. If Claude already
  does it right, delete the rule. If a rule must *always* hold, make it a hook (§6), not prose.
- **Underspecified asks are the #1 invocation failure.** Turn goals into testable requirements:
  inputs, deliverable, which files may change, which command proves it done.

---

## 5. Parallel safety: ownership, contracts, merge

1. **One file, one owner.** No two agents edit the same file — *including* shared resources
   (`pyproject.toml`, `app/tools/__init__.py`, a barrel `index.ts`, migrations). If a shared file
   must change, the lead edits it during integration. Our specs already enforce this; extend the
   ownership list to every shared file.
2. **Worktree + branch per agent.** Workers commit only their own file(s) to their branch; nobody
   touches `main`.
3. **Contract-first seams.** The lead writes and **freezes** the interfaces *before* the parallel
   phase — type stubs, the `@tool` signature, the `ViewModule` contract, an API shape. Workers
   code *to* the contract; if one needs to change it, it STOPs and the lead re-broadcasts. (Our
   `SHARED-BRIEF.md` "keep the public API identical to the stub" is exactly this.)
4. **Right-sized tasks.** Each agent's task should be describable in one sentence with a clear
   "done" test. Don't split one tightly-coupled feature across agents; don't give one agent eight
   loosely-related files.
5. **Sequential, gated merge.** Each worker reports `branch + SHA + test status`. The lead merges
   **one branch at a time, running the full suite after each** — so any breakage is trivially
   attributable to the branch just merged.

---

## 6. Verification & guardrails (close the loop)

Agents stop when work *looks* done. Move "done" out of the model's discretion.

- **Give every agent a runnable check** and tell it to iterate until green — tests, typecheck,
  lint, a screenshot diff. This is what lets the loop close without a human.
- **Evidence before claims.** Require the agent to paste the command it ran and its output. "No
  evidence = not done." Catches the false-completion failure.
- **Protect the tests.** Agents "make tests pass" by weakening or deleting them. Treat test files
  as immutable for the implementing agent (deny rule / PreToolUse hook).
- **Deterministic hooks beat advisory prose.** Hooks *guarantee* an action:
  - `PreToolUse` (Edit|Write) → block writes to files the agent doesn't own, to `.env`, to
    migrations, to `tests/`. Fires before permission checks, so it can't be bypassed.
  - `PostToolUse` (Edit|Write) → auto lint/format/typecheck the changed file, feed failures back.
  - `Stop` / `SubagentStop` → run `typecheck && lint && test`; block the turn until it passes
    (guard against loops with `stop_hook_active`).
- **Per-agent least privilege.** Set each sub-agent's `tools:` to only what its role needs —
  reviewers/planners get `Read, Grep, Glob` (no Write). Omitting `tools` grants *all* tools.
- **Fresh-context review.** Before counting work done, a reviewer agent sees only the diff + the
  criteria (not the reasoning that produced it) and reports gaps. Scope it to **correctness and
  requirement gaps, not style**, or it will invent findings. Our `/code-review` skill does this.
- **Structured completion report.** Force a per-requirement accounting so the agent can't
  hand-wave "done" (see template in §7).

---

## 7. Copy-paste kit

### 7a. Sub-agent spec skeleton

```markdown
---
name: <agent-name>
description: <one line — when to use it; "safe to run in parallel with peers">
tools: Read, Write, Edit, Bash, Grep, Glob   # least privilege; reviewers omit Write/Edit
model: sonnet
---

You are a <single role>. Your only job: <one sentence>.

## Orient first (read before writing)
- <spec/contract file>  ·  <conventions>  ·  <the data/files that actually exist — verify>

## Scope — you may ONLY create/edit:
- <exact/path/one.ext>
- <exact/path/two.test.ext>

## Invariants (do NOT change)
- Edit nothing outside Scope. No new dependencies. Do not weaken or delete any test.
- Keep the public API identical to the stub: <the frozen contract>.
- If a shared file needs changing, STOP and report it — do not edit it.

## How to build it
<the contract + 1 short worked example of input→output>

## Done when (verify before reporting)
1. `<test command>` passes — paste output.
2. `<typecheck>` and `<lint>` clean — paste output.
3. `git diff --stat` shows only Scope files.
Re-read Invariants + Done-when and confirm each. If any can't be met, STOP and report which + why.

## Report back
(1) files changed (2) ids/exports created (3) what you implemented (4) check results
(5) anything blocked or any shared-file change needed.

Reminder of non-negotiables: only touch Scope files; never weaken tests; run the checks;
STOP and report if blocked. Now complete the task.
```

### 7b. CLAUDE.md rules block (short, positive, high-signal)

```markdown
## Agent rules
- Before claiming any status, paste the command you ran and its output. No evidence = not done.
- Edit only the files in your task's scope; if a shared file must change, stop and ask.
- Never weaken or delete a test to make a suite pass.
- Use only libraries already in pyproject.toml / package.json.
- Plan first for any change touching 2+ files; confirm the plan before editing.
- Build/test: backend `cd backend && ./.venv/Scripts/python.exe -m pytest -q`;
  frontend `npx tsc --noEmit && npx eslint .`.
```

### 7c. Deterministic guardrail hooks (`.claude/settings.json`)

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [ { "type": "command",
          "command": "cd backend && ./.venv/Scripts/python.exe -m pytest -q" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command",
        "command": "cd backend && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m pytest -q" } ] }
    ]
  }
}
```

### 7d. Definition-of-done checklist (paste into the spec)

> Before reporting done, complete and paste this:
> - [ ] Every acceptance criterion implemented (list each + `file:line`)
> - [ ] typecheck / lint run — output pasted
> - [ ] tests added for each edge case; suite run — output pasted
> - [ ] `git diff --stat` shows only scope files
> - [ ] No test weakened or deleted

### 7e. Merge runbook (lead)

```
for each worker: collect branch + SHA + test status
verify branch is in scope (git diff --stat origin/main..branch)
merge branch 1 → run full suite → merge branch 2 → run full suite → …
on failure: kick back to the owning agent with the failing output
finally: /code-review against the plan in a fresh context
```

---

## 8. Failure-mode → mitigation

| Symptom | Root cause | Fix |
|---|---|---|
| "Did more than asked" | literal over-reach, overengineering | anti-overengineering clause; tight scope (§3) |
| "Did less than asked" | suggest-not-implement default | explicit action-default (§3) |
| Ignored a rule | rule buried mid-context / negative phrasing / CLAUDE.md bloat | top+bottom placement; positive phrasing; prune CLAUDE.md (§3–4) |
| Forgot the goal late in a run | goal drift / context rot | todo list + NOTES.md + re-grounding (§4) |
| Merge conflicts / lost work | overlapping file writes | one-file-one-owner + worktrees + ownership hook (§5–6) |
| Pieces don't fit together | parallel agents made conflicting implicit decisions | shared brief carries cross-boundary decisions; frozen contract (§2,§5) |
| "Tests pass" but they don't / weakened | reward hacking, false completion | protect tests; Stop-hook gate; evidence-before-claims; fresh-context review (§6) |
| Declared done prematurely | "looks done" is the only signal | runnable check + DoD gate (§6,§7d) |

---

## Sources

- [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic — Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system)
- [Cognition — Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents)
- [Claude Code — Best practices](https://code.claude.com/docs/en/best-practices) ·
  [Subagents](https://code.claude.com/docs/en/sub-agents) ·
  [Hooks](https://code.claude.com/docs/en/hooks-guide) ·
  [Common workflows](https://code.claude.com/docs/en/common-workflows)
- [Claude prompting best practices (Claude 4.x)](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [OpenAI — GPT-4.1 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide)
- [Lost in the Middle: How Language Models Use Long Contexts (Liu et al.)](https://arxiv.org/abs/2307.03172)
- [Chroma — Context Rot](https://www.trychroma.com/research/context-rot)
- [The Pink Elephant Problem (negative instructions)](https://eval.16x.engineer/blog/the-pink-elephant-negative-instructions-llms-effectiveness-analysis)
- [Anthropic — Code Review for Claude Code](https://claude.com/blog/code-review)
- [AGENTS.md standard](https://agents.md/)
- [Instruction Adherence in Coding Agent Configuration Files: A Factorial Study](https://arxiv.org/abs/2605.10039)
