# The Spark Hack Series — Presented by NVIDIA (Toronto)

Key details extracted from the [event Notion page](https://concrete-panther-c83.notion.site/The-Spark-Hack-Series-Presented-by-NVIDIA-36ff567d17cc80b59be6f8200cea8c36).

## At a glance

| | |
|---|---|
| **Event** | The Spark Hack Series — Toronto |
| **Hosts / Sponsors** | NVIDIA, ASUS, Antler |
| **Dates** | May 29–31, 2026 |
| **Format** | In person |
| **Venue** | Antler Office @ OneEleven — 325 Front St W, 4th Floor, Toronto |
| **Submission deadline** | **May 31, 11:00 AM** (one submission per team) |
| **Submit** | [Airtable submission form](https://airtable.com/app1GmXVsmDDGTXvy/pagqXe6ElIlXx6oa3/form) |
| **Discord** | https://discord.gg/egPwhV9y (primary comms — join ASAP, intro in `#introductions`) |

## The build challenge

Build a **functioning system** (not a slide deck or a thin API wrapper) that ingests raw
data, processes it **locally on the NVIDIA DGX Spark**, and produces a valuable result.
All submissions must use [City of Toronto open data](https://open.toronto.ca/) and align
with one of three **Challenge Tracks** (the track defines a theme of impact, not the scope —
build any solution from any of the datasets):

1. **Economic Systems** — improve how money flows through the city (businesses, workers, markets). Build agentic systems that help people/orgs make better economic decisions, unlock opportunities, or optimize costs.
2. **Public Services** — improve how people access and interact with city services. Build tools that simplify navigating public systems and make services more accessible and efficient.
3. **Urban Operations** — optimize how Toronto runs, from infrastructure to everyday city life. Build systems that improve how the city functions behind the scenes and in real time.

### Bounty
- **Best Use of [NVIDIA Nemotron](https://developer.nvidia.com/nemotron)** — a dedicated bounty for the team that best integrates Nemotron into their local solution. ([Nemotron asset hub](https://github.com/NVIDIA-NeMo/Nemotron))

## Judging criteria (100 points)

> Philosophy: *they are judging **systems engineering*** — a working system that ingests raw data, processes it locally on the DGX Spark, and produces a valuable result.

**1. Technical Execution & Completeness — 30 pts**
- 15 — Completeness: system completes the full data workflow without crashing.
- 15 — Technical Depth: real engineering under the hood (simulation, RAG, fine-tuning, custom logic) rather than a static dashboard or basic API wrapper.

**2. NVIDIA Ecosystem & Spark Utility — 30 pts**
- 15 — The Stack: uses at least one major NVIDIA library/tool (NIMs, RAPIDS, cuOpt, Modulus, NeMo). **Merely calling GPT-4 via API = 0 points here.**
- 15 — The "Spark Story": can articulate *why* it runs better on a DGX Spark (e.g. using the 128 GB unified memory to hold a video buffer + LLM context at once, or local inference for privacy/latency).

**3. Value & Impact — 20 pts**
- 10 — Insight Quality: insight is non-obvious and valuable.
- 10 — Usability: a real city planner / factory foreman could use it to make a decision tomorrow.

**4. Innovation & Execution — 20 pts**
- 10 — Creativity: novel combination of data or models.
- 10 — Performance: optimized for speed or scale.

## Submission checklist (due May 31, 11 AM — [submit here](https://airtable.com/app1GmXVsmDDGTXvy/pagqXe6ElIlXx6oa3/form))

- [ ] Team name
- [ ] Project description
- [ ] Challenge track selected
- [ ] **3–5 min demo video** (unlisted YouTube/Vimeo) showing the core loop live
- [ ] Repo link (public or invite judges) with a README containing:
  - [ ] Quick start (commands to run)
  - [ ] Tech stack & architecture diagram (simple is fine)
  - [ ] How to reproduce the demo (env vars, API keys, sample `.env`)
  - [ ] Any datasets / synthetic data used + provenance
  - [ ] Known limitations & next steps
- [ ] Deployed URL (if any) or a short screen capture of the working app
- [ ] Team roster (names, roles, contacts)

### Demo video structure (3–5 min)
1. Introduce your team (20–30s)
2. High-level elevator pitch / hook (30–40s)
3. Live demo of the core loop: input → processing → output (45–60s)
4. Narrate how you built it — architecture, stack, models, how the hardware shaped the design, challenges/tradeoffs (60–90s)
5. The "so what?" — why it deserves to win (20–30s)

## Agenda

- **Day 1 — May 29**: 5:00–6:00 PM Doors Open + Check-in · 6:00–6:45 PM Kick Off: Welcome & Hackathon Intro · (more sessions follow)
- **Day 2 — May 30**: full hacking day (see Notion page for session times)
- **Day 3 — May 31**: submissions due 11:00 AM; demos & judging

> Detailed per-session times for Days 2–3 weren't fully published on the page at extraction time — check the live Notion agenda for updates.

## Resources

- **Discord:** https://discord.gg/egPwhV9y
- **DGX Spark Playbooks:** [NVIDIA/dgx-spark-playbooks](https://github.com/NVIDIA/dgx-spark-playbooks) — step-by-step setup for AI/ML workloads on DGX Spark (Blackwell).
- **NVIDIA Nemotron:** [developer.nvidia.com/nemotron](https://developer.nvidia.com/nemotron) · [Nemotron asset hub](https://github.com/NVIDIA-NeMo/Nemotron)
- **Hardware:** NVIDIA DGX Spark / ASUS GX10 (128 GB unified memory) — see the page's "ASUS GX10 Wi-Fi Setup Guide" and DGX Spark livestreams.
- **City of Toronto open data:** https://open.toronto.ca/

### Venue Wi-Fi
- **Network:** `one11Guest`
- **Password:** `111@Front`
