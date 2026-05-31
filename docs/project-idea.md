# TransitRL — The Idea Behind This Project

## What it is

TransitRL is a **transportation-planning copilot for Toronto**. A planner, councillor, or resident asks a question in plain English — *"where are our transit deserts?"*, *"who's underserved relative to need?"*, *"improve access in Scarborough without raising downtown commute times"* — and a local language model answers with maps, numbers, and a plain-language rationale. Behind the conversation is a toolbox of real analyses: accessibility and equity diagnostics, what-if simulation, and a reinforcement-learning optimizer that can *search* for better stop layouts when the question calls for it.

It compresses what is normally a months-long, expert-driven planning study into a seconds-long, legible loop that someone without GIS training can actually use. And it's built entirely on **open weights and open public data**, so it's reproducible and free of vendor lock-in — a deliberate choice for something pitched as a public-sector tool.

## The reframe: a copilot, not a single trick

The natural first version of this project is narrow: *an RL agent that learns where bus stops should go.* That's a compelling demo, but a planner's real job is broader — they **diagnose** problems, **test** hypotheses, weigh **equity**, and **justify** decisions. So the optimizer is not the product; it's **one tool among many** that the agent reaches for only when a question needs a machine to search.

Most planner questions don't need optimization at all. "Which wards have the worst reliability for seniors?" is a diagnosis. "What if I move this stop two blocks east?" is a simulation. "Who loses access under this plan?" is attribution. A copilot that handles all of these — and calls the RL optimizer only when asked to *find* a layout — is something a city can **generally query**, not a one-trick demo.

## The core loop

The experience is a conversation with an agent that has tools:

1. **Ask.** The user states a goal or question in plain English.
2. **Orchestrate.** The language model decides which tools to call and in what order — diagnose, simulate, optimize, explain — and runs them against the city's open-data substrate.
3. **Answer.** Results come back as maps, metric tables, and a plain-language explanation. When the optimizer runs, the user watches the agent learn live as stops shift across the map.

The civic question *"who gets left behind?"* becomes a visible output rather than a buried assumption — surfaced explicitly by an equity-diagnostic tool and named in plain language by the model.

## System architecture

Four cooperating components, connected by a tool protocol:

- **Language interface (the open model)** sits at the front, turning English into tool calls and tool results back into English.
- **MCP tool layer (`transitrl-mcp`)** exposes the city's analyses as a typed, composable toolbox the model orchestrates. This is what makes it an *agentic system* rather than a chat wrapper — and what lets the same toolbox serve any model. *(See [Agent Tools & MCP Layer](agent-tools.md) for the full toolbox.)*
- **Reinforcement-learning agent + simulation environment** — the optimizer and the city it acts on, exposed as the heaviest tool in the box.
- **Map frontend** renders everything and animates the learning in real time.

The model wraps the toolbox as its human-facing bookends; the RL agent and simulation form a tight closed loop *inside* one of those tools.

## The toolbox (what the model can do)

Five families, mirroring how a planner thinks — **understand → diagnose → simulate → optimize → explain**:

- **Understand** — `get_city_grid`, `profile_area`, `list_transit`, `compare_areas`: read the current state of the city.
- **Diagnose** — `compute_accessibility`, `equity_gap_report`, `reachability`, `estimate_demand`, `reliability_report`: find the problems.
- **Simulate** — `simulate_change`, `diff_scenarios`, `constraint_check`: test a hypothesis instantly.
- **Optimize** — `parse_goal`, `optimize_layout`, `propose_candidates`: let the machine search for a layout that meets a goal.
- **Explain** — `who_is_affected`, `explain_result`, `generate_brief`: narrate the trade-off and export a council-ready memo.

Every tool is backed by specific open datasets — see the dataset→tool traceability matrix in [Agent Tools §4](agent-tools.md#4-dataset--tool-traceability).

## The reinforcement-learning formulation

The optimizer (`optimize_layout`) is the technical heart, modeled as a custom Gymnasium environment.

The city is a grid — a manageable resolution like 20×20 or 30×30 — where every cell carries real attributes: how many people live there, their income profile, and where the jobs and destinations are. This grid is effectively a multi-channel image of Toronto: one channel for population, one for current stop locations, one for income/equity, one for destinations. It's the *same* grid the diagnostic tools read, so every tool's results are mutually consistent.

The observation the agent sees is that stacked grid. Representing the city as a multi-channel image means the policy network is a **CNN** — the same architecture as image classification, except the head outputs action values or probabilities instead of class scores. The convolutional layers learn spatial structure (density gradients, coverage gaps) the same way they'd learn edges and textures in a photo.

The **action space** is kept discrete for training stability: the agent selects one stop and nudges it one cell in a cardinal direction, or picks from a small set of candidate relocation cells. Discrete actions keep the problem tractable for standard algorithms.

The **reward** is where the policy's "values" live — a weighted combination of four terms, and it's exactly this weighting that the model writes when it translates an English goal (`parse_goal`):

- **Coverage** — population within walking distance of any stop, rewarding broad reach.
- **Travel-time proxy** — summed distance from population centroids to the nearest stop, penalizing leaving people far from service.
- **Equity** — extra weight on low-income cells so the agent can't simply chase dense affluent corridors and ignore the people who depend on transit most.
- **Constraint penalties** — minimum spacing between stops and proximity to a route line, which stop the agent from gaming the reward by piling stops on a single hotspot.

Each environment step applies the chosen move, the simulation recomputes the metrics, and the change in the weighted score is returned as reward. An episode is a fixed number of moves, after which the layout resets. Training uses **Stable-Baselines3** — PPO with a CNN policy as the stable default, or DQN with a CNN as the simpler variant — rather than a hand-rolled algorithm.

## The simulation engine

Underneath the RL is a lightweight accessibility model, not a full traffic simulator. After each move it answers: how much of the population now falls within a walking buffer of a stop, how far is the average person from service, and how do those numbers break down by income geography. The same engine backs the `simulate_change` and `compute_accessibility` tools, so a hand-drawn what-if and a step inside RL training compute identically. Keeping the sim to walk-access and single-corridor effects — deliberately excluding multi-leg trips with transfers — is what makes it fast enough to run thousands of times during training and honest enough to defend.

## The open model integration

The open model is **NVIDIA Nemotron**, served locally through a **NIM** (with **Qwen3 via Ollama** as a fallback) — chosen because it's strong at the structured-output, reasoning, and tool-calling the agent needs, runs on local hardware, and targets the hackathon's dedicated Nemotron bounty. It plays three roles:

- It **orchestrates** — reading the user's question and deciding which MCP tools to call and in what sequence.
- It **translates** — turning an English goal into concrete reward weights (structured JSON) for the optimizer.
- It **narrates** — reading the before/after metrics and the agent's moves and explaining the trade-offs in human terms; as a stretch, it can **propose candidate relocations** to warm-start exploration.

Notably, the project has RL on both sides of the interface: the planning agent learns by reinforcement, and the open model guiding it was itself post-trained with large-scale RL.

## Data and stack

- **Network backbone** — TTC + GO/Metrolinx GTFS feeds (every route and stop).
- **Demographics & equity** — Statistics Canada census dissemination areas plus the Ontario Marginalization Index (population, income, marginalization).
- **Boundaries & walk network** — Toronto Open Data (neighbourhoods, centreline, pedestrian network).
- **Walk distances** — computed with geometric buffers rather than a heavy routing engine.

The backend runs **Gymnasium**, **Stable-Baselines3**, and **PyTorch**, with spatial work (rasterization, buffers, joins) accelerated by **RAPIDS cuDF/cuSpatial** and travel-time/placement by **cuOpt**. It's exposed through **FastAPI**, with the MCP server on top and a **WebSocket** streaming each training episode to the frontend so the map animates as the agent learns. The frontend is **React** with **MapLibre** and **deck.gl** for the animated dots, heatmaps, and density layers that carry the visual payoff. On the DGX Spark, the rasterized city grid, the RL replay buffer, and the Nemotron context all live in **128 GB of unified memory** at once — so what-if simulations return sub-second and the explanation is reasoned locally, with no data leaving the device.

## Scope and honesty

TransitRL is explicitly an **accessibility and equity model, not a demand forecast**. The demand tool surfaces *latent* demand from land use and population — it does not predict ridership. The simulation is walk-access and single-corridor; it deliberately excludes multi-leg transfer trips. It's a tool for asking better questions early and seeing trade-offs fast — not a replacement for detailed engineering studies. Naming that limit up front, and inside the exported briefs, is part of the design — both because it's true and because it's the first thing a transit-literate judge will probe.
