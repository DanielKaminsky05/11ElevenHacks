# TransitRL — Runtime Agent Reliability

How to make the **runtime planning agent** (Nemotron-Nano-9B-v2 via an **NVIDIA NIM** on the DGX Spark / GB10; see §7 and [`backend-hosting-plan.md`](backend-hosting-plan.md)) reliably (1) **interpret** a user's
chat message, (2) **call the right tools with valid arguments**, and (3) **execute a workflow in
order without skipping steps or inventing numbers**. This is the execution counterpart to
[`agent-workflows.md`](agent-workflows.md) (the *what* and the *order*) and
[`agent-tools.md`](agent-tools.md) (the *tools*). For build-time coding sub-agents, see
[`agent-orchestration.md`](agent-orchestration.md) instead.

> **The one idea:** for a known workflow, **don't hope the model behaves — make misbehaviour
> structurally impossible.** Enforce step order with code-level gates, force arguments through
> typed schemas, and require every number in the answer to cite the tool that produced it.
> Behavioural techniques (good docstrings, few-shot golden paths) make the model *want* to do the
> right thing; structural techniques make it *unable* to do the wrong thing. Use both.

The three failure surfaces and where they're addressed:

| Failure | Example | Section |
|---|---|---|
| Misreads intent / wrong workflow / drops a constraint | "improve access **without hurting downtown**" → ignores the guardrail | §1 |
| Wrong tool / hallucinated name / bad arguments | calls `optimize_layout` when the user proposed a specific change | §2 |
| Skips steps / invents numbers / stops early | recommends a route with no `who_is_affected`, quotes made-up ridership | §3 |

---

## 1. Interpret the chat → a typed goal + workflow

Turn fuzzy language into a **typed object** and a chosen workflow before any heavy tool runs.

- **1.1 Route first, with an LLM router (thin).** A first, cheap call classifies the message into
  one of the ~10 workflows from `agent-workflows.md` (`new-route`, `transit-deserts`,
  `evaluate-proposal`, `budget-constrained`, `target-group`, …) and emits
  `{workflow_id, confidence}`. Keep the router thin — it only picks the workflow and extracts
  params, then hands off to that workflow's prompt+toolset (separation of concerns: tuning one
  workflow can't regress the others).
- **1.2 Add a fast semantic pre-pass.** Pre-embed 10–20 paraphrases per workflow ("transit
  desert", "areas left behind", "underserved" → `transit-deserts`) and route by nearest-neighbour
  first; fall back to the LLM router only when the top-2 are close. Cheap, deterministic, and
  paraphrase-robust.
- **1.3 Extract a typed `TransitGoal` (this is `parse_goal`).** One structured-output call fills:
  `{ workflow, area, target_group, optimize_for, budget, constraints[] }`. Per-field descriptions
  act as inline instructions; required-vs-optional makes missing slots detectable (→ clarify).
- **1.4 Make negative constraints a first-class typed slot.** Negation is the most-dropped signal.
  Don't let "without hurting downtown commutes" live in prose — force it into
  `constraints: [{metric, direction: must_not_worsen|cap|maximize, area}]`. Few-shot the field with
  negation paraphrases ("don't make X worse", "while keeping Y", "as long as Z holds"). Downstream
  these become hard guardrails the result is checked against (§3.6).
- **1.5 Ground domain vocabulary to metrics.** Maintain a glossary that binds jargon to concrete
  metrics so the same word always means the same thing: "transit desert" → `pct_pop >400m_from_stop`;
  "left behind"/"underserved" → ON-Marg / equity index; "low-income" → census LIM threshold;
  "Scarborough" → a specific boundary id. Inject it into the router/extractor prompt.
- **1.6 Clarify only when it's worth it (margin + risk).** If the top-2 workflows are within a
  margin, or a *high-impact* slot is missing (target area, an unparsed guardrail), ask **one**
  targeted question that resolves the most decision-relevant ambiguity. For low-risk slots
  (missing budget → "unconstrained"), assume a default and **state it** so the planner can correct.
  Don't interrogate.

---

## 2. Call tools correctly

Most tool-calling errors are selection errors, argument errors, or recovery failures — attack each.

**Design for correct selection**
- **2.1 Few, distinct, workflow-shaped tools.** More tools ≠ better; near-duplicates are extra
  ways to pick wrong. Keep ≲15–20 live. The danger is *within* a family — if two diagnostics both
  take a region, merge into `diagnose_region(region, metrics:[…])` or make the docstrings sharply
  contrastive.
- **2.2 Namespace names `family_action_object`.** `transit_simulate_change` vs
  `transit_optimize_layout` makes the verb (`simulate` vs `optimize`) explicit in the name and cuts
  hallucinated names — these two are the classic confusion pair here.
- **2.3 Contrastive docstrings with when-to-use AND when-NOT.** The docstring *is* the description
  the model selects from. State purpose, the triggering situation, what it returns, and the
  contrast:
  ```python
  @tool(SimulateChangeArgs)
  def simulate_change(args):
      """Predict the effect of a SPECIFIC, user-proposed change (e.g. 'add stops on Finch').
      Returns before/after coverage, jobs, equity. Use when the user already has a change in mind.
      Do NOT use to discover the best change — use optimize_layout. Do NOT use for current state —
      use list_transit / compute_accessibility."""
  ```
- **2.4 Routing policy in the system prompt.** A short numbered policy expresses cross-tool order
  the per-tool docs can't: "Resolve the area with `profile_area`/`get_city_grid` before diagnosing;
  'what is' → diagnostics, 'what if' → `simulate_change`, 'what should' → `optimize_layout`;
  greetings → no tool." Include one example of correctly choosing **no** tool.

**Design for correct arguments**
- **2.5 Make invalid states unrepresentable (Pydantic).** `Literal`/enums for choices,
  `Field(ge=, le=)` for bounds, typed sub-models for structured args — collapses the space the
  model can hallucinate into. Highest-leverage argument fix.
- **2.6 Per-field descriptions: format, units, provenance.** Name `area_id` not `area`; say
  "canonical id from `get_city_grid`, not a free-text place name"; annotate **units** everywhere
  (metres, minutes, %) — transit metrics are unit-heavy and unitless numbers fail silently. This
  also teaches the model to **chain** (use a prior tool's id) instead of inventing one.
- **2.7 Minimize required args; inject known values server-side.** Every required field is a
  failure opportunity. If the session knows the city, don't expose it as a model-filled arg; default
  `mode="all"`, thresholds, etc.
- **2.8 Enforce the schema at decode time + `tool_choice`.** Confirm the NIM/Nemotron deployment
  applies guided JSON decoding from each tool's schema (eliminates malformed-JSON / out-of-enum
  calls). Use `tool_choice`: `auto` for conversational turns, `required` when the turn is clearly
  actionable, named to force a deterministic first step. *Pin a NIM/model version with a known-good
  tool parser and verify `parallel_tool_calls` support before relying on it.* **✓ On our stack the model is served by a NIM (Nemotron-Nano-9B-v2 DGX Spark build), so decode-time guided JSON holds — see §7.**

**Design for recovery**
- **2.9 Validation-error retry loop.** On `ValidationError`, return `.errors()` (which field, what
  constraint) to the model as the tool result and let it retry, capped at ~2. Most bad-arg calls are
  recoverable *if the model is told what was wrong*.
- **2.10 Steering error messages.** Errors should name the fix and the right next tool, not just
  "invalid": `"area_id 'downtown' isn't valid — call get_city_grid first for a canonical id."` /
  `"No proposed_change supplied; to find a change use optimize_layout instead."` (recovery that also
  corrects *selection*).
- **2.11 Return results that enable the next call.** Tool outputs should carry the
  human-meaningful ids/fields the next tool needs (return `{area_id, name}`, not opaque blobs),
  truncated with a `detail: Literal["summary","full"]` arg. Good outputs make correct chaining the
  path of least resistance.

---

## 3. Execute the workflow reliably (order + grounding)

The route workflow is **fixed**: `understand → diagnose → parse_goal → optimize_layout →
(simulate + who_is_affected) → brief`, with the hard rule *diagnose before optimize; attribute
before recommend.* Because it's fixed, enforce it structurally.

- **3.1 Orchestrate the known path; don't let the model choose the order.** Anthropic: use a
  **workflow** (predictable) when the path is known, reserve autonomous agents for open-ended
  problems. Encode the steps in orchestration code so `optimize_layout` literally isn't invocable
  until `diagnose` has returned output the orchestrator passes forward.
- **3.2 Programmatic gates / state machine between steps.** `OPTIMIZE` requires state `DIAGNOSED`;
  `BRIEF` requires `ATTRIBUTED` (`who_is_affected` has run). The orchestrator refuses out-of-order
  calls — making both halves of the domain rule impossible to violate, not merely requested.
- **3.3 Plan-and-Execute / ReWOO with evidence placeholders.** Have the model emit the full ordered
  plan up front, referencing future outputs by placeholder:
  `#E1=diagnose(area); #E2=parse_goal(...); #E3=optimize_layout(#E2); #E4=simulate(#E3);
  #E5=who_is_affected(#E3); brief(#E3,#E4,#E5)`. The brief can only cite `#E4`/`#E5`, so invented
  numbers have **no slot to live in**. Planning the whole task up front also kills the myopic
  step-skipping of pure ReAct.
- **3.4 Golden-path few-shot trajectory.** Put 1–2 complete worked transcripts in the system prompt
  (thought → tool call → observation → … → grounded brief) for a sample neighbourhood that always
  diagnoses first, always names who loses service, and tags every number with its source tool.
  Models generalize exemplar *ordering and style*.
- **3.5 Grounding mandate: every number cites its tool.** Require claims like
  `"+1,240 residents within 400 m (source: simulate_change)"`,
  `"312 households lose direct access (source: who_is_affected)"`. Any number without a source tag
  is invalid by rule — fabrication becomes detectable. (This is H9 from `agent-workflows.md`:
  accessibility model, *not* a ridership forecast — never invent demand numbers.)
- **3.6 Schema-validated step outputs + guardrail check.** `diagnose` must return a populated `gap`
  before the gate opens; the `brief` schema requires non-empty `affected_groups` whose values
  reference upstream tool ids → enforces "attribute before recommend." A separate output guardrail
  re-checks the result against the typed `constraints[]` from §1.4 (did "downtown commute time" stay
  flat?).
- **3.7 Reflection pass before finalizing (separate call).** A checker — *not* the model that wrote
  the brief — verifies: was diagnose run? was `who_is_affected` run before the recommendation? does
  every number cite a tool? are all steps present and constraints honoured? If any fail, loop back.
- **3.8 Termination = full workflow done, not "looks done."** Define completion as "`brief` has run
  and references `simulate` + `who_is_affected` outputs." Add a **minimum-required-tools** assertion
  (diagnose, optimize_layout, simulate, who_is_affected, brief all appear) plus a max-steps cap and
  repeat detection. RLHF models are action-biased and stop when output looks plausible — make "done"
  machine-checkable.
- **3.9 Thinking on for planning/diagnosis, off for mechanical steps.** Spend reasoning where
  ordering and the causal rule are decided (understand, diagnose, the reflection pass); keep it
  off/low for `parse_goal` argument extraction and deterministic tool calls. (Matches the latency
  policy already in `agent-workflows.md` §5.8.)

---

## 4. Worked example — "improve access for low-income Scarborough without hurting downtown commutes"

1. **Interpret (§1).** Semantic pre-pass + router → `target-group` (primary) **plus** an
   `evaluate-proposal` guardrail check (multi-intent). `parse_goal` →
   `{area:"Scarborough", target_group:"low_income", optimize_for:"accessibility",
   constraints:[{metric:"commute_time", direction:"must_not_worsen", area:"downtown"}]}`.
   Glossary maps "low-income" → LIM threshold, "Scarborough" → boundary id. Area present, guardrail
   captured → no clarification needed.
2. **Call tools (§2).** `tool_choice` forces `profile_area`/`get_city_grid` first (typed `area_id`);
   diagnostics chosen over simulation because intent is "improve", not "what if".
3. **Execute (§3).** Gates run `equity_gap_report` + `reachability` (diagnose) → `optimize_layout`
   with the equity weight → `simulate_change` + `who_is_affected(by=income)` → output guardrail
   confirms downtown commute time didn't worsen → reflection pass → `brief` with every number tagged
   to its tool and a winners/losers table.

If the model had tried to jump to `optimize_layout` first, the gate (§3.2) blocks it; if it quoted a
ridership number, the grounding rule (§3.5) flags it; if it dropped the downtown guardrail, the
output guardrail (§3.6) catches it.

---

## 5. Measure it (you can't fix what you don't track)

- **5.1 Trajectory evals, not just final answers.** Build a fixture set of neighbourhoods with
  assertions: diagnose-before-optimize, who_is_affected-before-brief, every brief number matches a
  tool output, all steps present, constraints honoured. τ-bench shows even strong agents pass <50%
  and are *inconsistent* across runs — so measure **pass^k** (e.g. pass^5), not best-case.
- **5.2 Paraphrase robustness + confusion-pair tracking.** Test each workflow with varied phrasings
  (naturalistic paraphrases drop tool-selection accuracy 13–19 pts) and track wrong-tool confusion
  pairs (especially `simulate_change`↔`optimize_layout`); iterate docstrings until confusion drops.
- **5.3 Instrument every call.** Log per-tool error rate, wrong-tool rate, no-call-when-needed,
  retry count, latency. Run tool turns at low temperature (0.0–0.2) — Databricks measured up to a
  10% accuracy swing vs 0.7.

---

## 6. Implementation checklist for TransitRL

- [ ] `parse_goal` returns a typed `TransitGoal` with a first-class `constraints[]` slot (§1.3–1.4).
- [ ] A domain glossary (jargon → metric/boundary id) injected into the router/extractor (§1.5).
- [ ] Tools namespaced; `simulate_change`/`optimize_layout` docstrings made contrastive (§2.2–2.3).
- [ ] Every tool arg uses enums/bounds + unit-annotated, provenance-stating field descriptions (§2.5–2.6).
- [ ] Structured output for `parse_goal` backed by the NIM's decode-time guided JSON (free schema enforcement); `tool_choice`/`parallel_tool_calls` supported; image pinned to `…nemotron-nano-9b-v2-dgx-spark:latest` (§2.8, §7).
- [ ] Validation-error retry loop with steering messages around every tool (§2.9–2.10).
- [ ] Route workflow runs through code-level **gates** (diagnose→optimize→attribute→brief) (§3.1–3.2).
- [ ] Brief schema requires tool-sourced numbers + non-empty `affected_groups`; output guardrail
      re-checks `constraints[]` (§3.5–3.6).
- [ ] Reflection pass + machine-checkable completion (min-required-tools) before returning (§3.7–3.8).
- [ ] Trajectory eval set with pass^k + paraphrase + confusion-pair tracking in CI (§5).

---

## 7. On-box reality: NIM on DGX Spark (2026-05-31)

The runtime model is served by an **NVIDIA NIM**, not Ollama — the GB10 build
`nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark` (Nemotron-Nano-9B-v2, hybrid
Mamba-2/Attention, tool-calling), OpenAI-compatible and launched via
[`backend/scripts/run_nim.sh`](../backend/scripts/run_nim.sh) on **`http://localhost:8001/v1`**
(port 8000 on the box is taken by an unrelated service). This is the right call for the
Nemotron bounty + NVIDIA-ecosystem rubric, and — unlike a generic Ollama server — it **restores**
the decode-time guarantees this doc was drafted around, rather than forcing work-arounds:

1. **Decode-time guided JSON is back (§2.8).** NIM enforces each tool's JSON Schema at decode via
   its xgrammar path, so the "eliminates malformed-JSON / out-of-enum calls" guarantee **holds for
   free**. The §2.9 validation-retry loop stays as defense-in-depth (we already implement it in
   `parse_goal` and the `/chat` loop), but it is a backstop, not the primary guard.
2. **`tool_choice` semantics are supported (§2.8).** NIM's OpenAI endpoint honors
   `tool_choice: "required"`/named and `parallel_tool_calls`. We still prefer the orchestrator
   gate (§3.2) to enforce "a tool must run" for the fixed-route workflow — but we can lean on
   `tool_choice` where convenient.
3. **Version pin (§2.8):** image tag `…-dgx-spark:latest` (`1.0.0-variant`). Re-run the §5
   trajectory evals if the image tag changes.

**Validation status.** A live tool-calling smoke test (`backend/scripts/nim_smoke_test.py`) plus a
real `POST /planner` round-trip confirm the model emits parseable `tool_calls`/structured weights
against our schemas. (An earlier exploratory run on Ollama `nemotron3:33b` got tool selection +
args correct 3/3 with unstated-arg inference, e.g. `"on foot"`→`mode:"walk"` — evidence the tool
schemas themselves are well-designed; the NIM is the shipped runtime.)

**Net:** the *structural* defenses in §3 (code-level gates, plan-with-placeholders, the grounding
mandate, the reflection pass) remain the backbone of reliability — and with NIM's decode-time
schema enforcement layered back on top, §2's malformed-call risks are low for our current schemas.

## Sources

- [Anthropic — Building effective agents (workflows vs agents, routing, prompt-chaining gates)](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic — Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic — Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [OpenAI — A Practical Guide to Building Agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) ·
  [Function calling guide](https://developers.openai.com/api/docs/guides/function-calling) ·
  [Agents SDK — Handoffs](https://openai.github.io/openai-agents-python/handoffs/) ·
  [Guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [NVIDIA NIM for LLMs — Function (Tool) Calling](https://docs.nvidia.com/nim/large-language-models/latest/function-calling.html)
- [Berkeley Function-Calling Leaderboard (BFCL)](https://gorilla.cs.berkeley.edu/leaderboard.html) ·
  [Databricks — Unpacking Function-Calling Evaluation](https://www.databricks.com/blog/unpacking-function-calling-eval)
- [Plan-and-Solve Prompting (arXiv 2305.04091)](https://arxiv.org/abs/2305.04091) ·
  [ReWOO (arXiv 2305.18323)](https://arxiv.org/abs/2305.18323) ·
  [ReAct (Prompting Guide)](https://www.promptingguide.ai/techniques/react) ·
  [LangChain — Plan-and-Execute agents](https://www.langchain.com/blog/planning-agents)
- [τ-bench (arXiv 2406.12045)](https://arxiv.org/pdf/2406.12045) ·
  [TRAJECT-Bench (arXiv 2510.04550)](https://arxiv.org/pdf/2510.04550)
- [LlamaIndex — Router Query Engine & selectors](https://docs.llamaindex.ai/en/stable/module_guides/querying/router/) ·
  [Pydantic AI — validation retries (ModelRetry)](https://ai.pydantic.dev/tools-advanced/)
- [Ask or Assume? Uncertainty-Aware Clarification (arXiv 2603.26233)](https://arxiv.org/html/2603.26233v1) ·
  [Zero-shot Slot Filling with LLMs (arXiv 2411.18980)](https://arxiv.org/html/2411.18980v1)
