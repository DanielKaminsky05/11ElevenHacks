# TransitRL — Runtime Agent Reliability

How to make the **runtime planning agent** (Nemotron 3 — `nemotron3:33b` via **Ollama** on the GX10, *not* NIM; see §7 and [`backend-hosting-plan.md`](backend-hosting-plan.md)) reliably (1) **interpret** a user's
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
  tool parser and verify `parallel_tool_calls` support before relying on it.* **⚠️ On our stack the model is served by Ollama, not NIM, so decode-time guided JSON is NOT guaranteed — see §7 for what changes.**

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
- [ ] Structured output for `parse_goal` via Ollama `format` (JSON Schema) **or** vLLM guided decoding — we run **Ollama, not NIM**, so there's no free decode-time enforcement; `tool_choice`/`parallel_tool_calls` support verified on Ollama 0.24; model pinned to `nemotron3:33b` (§2.8, §7).
- [ ] Validation-error retry loop with steering messages around every tool (§2.9–2.10).
- [ ] Route workflow runs through code-level **gates** (diagnose→optimize→attribute→brief) (§3.1–3.2).
- [ ] Brief schema requires tool-sourced numbers + non-empty `affected_groups`; output guardrail
      re-checks `constraints[]` (§3.5–3.6).
- [ ] Reflection pass + machine-checkable completion (min-required-tools) before returning (§3.7–3.8).
- [ ] Trajectory eval set with pass^k + paraphrase + confusion-pair tracking in CI (§5).

---

## 7. On-box reality & validated baseline (Ollama, not NIM — 2026-05-31)

This doc was drafted assuming **Nemotron via NIM**. The live GX10 actually serves the model
through **Ollama 0.24.0** (`nemotron3:33b`, OpenAI-compatible at `http://localhost:11434/v1`,
pinned `keep_alive=-1`). That's the right call for the Nemotron bounty + co-run headroom (see
[`backend-hosting-plan.md`](backend-hosting-plan.md)) — but it changes three reliability
assumptions above. First, the measured baseline (live tool-calling test, `temperature=0`):

- **Tool selection + args correct 3/3** — the model chose `equity_gap_report` vs
  `compute_accessibility` appropriately, emitted **valid JSON**, and *inferred unstated args from
  language* (`"on foot"`→`mode:"walk"`, `"within 400 m"`→`threshold_m:400`). So §2's
  selection/argument risks are **low for our current schemas** — but keep the §5 evals running as
  the tool count grows and as other tenants on the shared box change what's loaded.
- **Speed:** ~67–81 tok/s decode, ~2,550 tok/s prefill; a tool turn is **~0.8–1.0 s with
  `/no_think`** vs **4.8 s** thinking-on → confirms the §3.9 latency policy with real numbers
  (thinking off for tool-selection/`parse_goal`, on for narration).

**What Ollama-not-NIM changes:**

1. **No decode-time guided JSON by default (affects §2.8).** Ollama doesn't enforce each tool's
   schema at decode the way NIM's xgrammar path does, so the "eliminates malformed-JSON /
   out-of-enum calls" guarantee **does not hold for free.** Mitigate, in order: (a) for the
   structured `parse_goal` step, pass a **JSON Schema via Ollama's `format`** field rather than
   relying on free-form output; (b) treat the **§2.9 validation-error retry loop as mandatory,
   not optional**, around every tool call; (c) if structured output proves shaky at scale, serve
   just the structured/agentic steps via **vLLM + Marlin** (xgrammar guided decoding) — the
   optional hardening path already in the hosting plan.
2. **Verify `tool_choice` semantics before relying on them (affects §2.8).** Confirm Ollama
   0.24's OpenAI endpoint honors `tool_choice: "required"`/named and `parallel_tool_calls`. If it
   doesn't, **enforce "a tool must run" with the orchestrator gate (§3.2), not `tool_choice`** —
   which is what we want anyway for the fixed route workflow.
3. **The §2.8 version pin is `nemotron3:33b` on Ollama 0.24.0** (tool parser validated
   2026-05-31). Re-run the trajectory evals (§5) if the model tag or Ollama version changes — or
   if a co-tenant swaps the loaded model out from under us on the shared box.

**Net:** the *structural* defenses in §3 (code-level gates, plan-with-placeholders, the grounding
mandate, the reflection pass) matter **more** on Ollama, because we can't lean on decode-time
schema enforcement — they're what keep us reliable without it.

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
