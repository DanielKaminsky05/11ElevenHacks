# TransitRL — The Idea Behind This Project

## What it is

TransitRL is an interactive decision-support tool that learns where bus stops should go. A user describes a transit goal in plain English; a reinforcement-learning agent learns the optimal stop placement to achieve that goal on a real map of Toronto; and an open language model explains what the agent did and who it helped or hurt. It compresses what is normally a months-long, expert-driven planning study into a seconds-long, legible loop that a planner, a councillor, or a resident can actually use.

The system is built entirely on open weights and open public data, so it's reproducible and free of vendor lock-in — a deliberate choice for something pitched as a public-sector tool.

## The core loop

The whole experience is three acts:

1. **Goal.** The user types a goal: *"improve access for low-income neighbourhoods in Scarborough without increasing downtown commute times."*
2. **Learning.** An RL agent relocates stops across the map, one move at a time, learning over many episodes — and the user watches it learn live as the stops shift.
3. **Explanation.** When the agent converges, the open model narrates the outcome in plain language: which stops moved, which areas gained access, who lost out, and the trade-off the user implicitly chose.

The civic question *"who gets left behind?"* becomes a visible output rather than a buried assumption.

## System architecture

There are four cooperating components:

- **Language interface (the open model)** sits at the front, turning English goals into reward functions and turning results back into English.
- **Reinforcement-learning agent** is the optimizer.
- **Simulation environment** — the city itself — is what the agent acts on and learns from.
- **Map frontend** renders everything and animates the learning in real time.

The RL agent and the simulation form a tight closed loop; the language model wraps that loop as its human-facing bookends.

## The reinforcement-learning formulation

This is the technical heart, modeled as a custom Gymnasium environment.

The city is a grid — a manageable resolution like 20×20 or 30×30 — where every cell carries real attributes: how many people live there, their income profile, and where the jobs and destinations are. This grid is effectively a multi-channel image of Toronto: one channel for population, one for current stop locations, one for income/equity, one for destinations.

The observation the agent sees is that stacked grid. Representing the city as a multi-channel image means the policy network is a **CNN** — the same architecture as image classification, except the head outputs action values or probabilities instead of class scores. The convolutional layers learn spatial structure (density gradients, coverage gaps) the same way they'd learn edges and textures in a photo.

The **action space** is kept discrete for training stability: the agent selects one stop and nudges it one cell in a cardinal direction, or picks from a small set of candidate relocation cells. Discrete actions keep the problem tractable for standard algorithms.

The **reward** is where the policy's "values" live — a weighted combination of four terms:

- **Coverage** — population within walking distance of any stop, rewarding broad reach.
- **Travel-time proxy** — summed distance from population centroids to the nearest stop, penalizing leaving people far from service.
- **Equity** — extra weight on low-income cells so the agent can't simply chase dense affluent corridors and ignore the people who depend on transit most.
- **Constraint penalties** — minimum spacing between stops and proximity to a route line, which stop the agent from gaming the reward by piling stops on a single hotspot.

Each environment step applies the chosen move, the simulation recomputes the metrics, and the change in the weighted score is returned as reward. An episode is a fixed number of moves, after which the layout resets. Training uses **Stable-Baselines3** — PPO with a CNN policy as the stable default, or DQN with a CNN as the simpler variant — rather than a hand-rolled algorithm.

## The simulation engine

Underneath the RL is a lightweight accessibility model, not a full traffic simulator. After each move it answers: how much of the population now falls within a walking buffer of a stop, how far is the average person from service, and how do those numbers break down by income geography. Keeping the sim to walk-access and single-corridor effects — deliberately excluding multi-leg trips with transfers — is what makes it fast enough to run thousands of times during training and honest enough to defend.

## The open model integration

The open model is **Qwen3**, served locally through **Ollama** — chosen because it's small enough for consumer hardware, permissively licensed (Apache 2.0), and strong at the structured-output and reasoning the project needs. It plays two essential roles and one optional one:

- It **translates** the user's English goal into concrete reward weights (structured JSON).
- It **narrates** the converged result, reading the before/after metrics and the agent's moves and explaining the trade-offs in human terms.
- As a stretch, it can **propose candidate relocations** to warm-start the agent's exploration.

Notably, the project has RL on both sides of the interface: the planning agent learns by reinforcement, and the open model guiding it was itself post-trained with large-scale RL.

## Data and stack

- **Network backbone** — the TTC GTFS feed (every route and stop).
- **Demographics** — Statistics Canada census dissemination areas (population and income).
- **Boundaries** — Toronto Open Data.
- **Walk distances** — computed with geometric buffers rather than a heavy routing engine.

The backend runs **Gymnasium**, **Stable-Baselines3**, and **PyTorch**, exposed through **FastAPI**, with a **WebSocket** streaming each training episode to the frontend so the map animates as the agent learns. The frontend is **React** with **MapLibre** and **deck.gl**, which handles the animated dots, heatmaps, and density layers that carry the visual payoff.

## Scope and honesty

TransitRL is explicitly an **accessibility and equity model, not a demand forecast**. It's a tool for asking better questions early and seeing trade-offs fast — not a replacement for detailed engineering studies, and not a claim to predict ridership. Naming that limit up front is part of the design, both because it's true and because it's the first thing a transit-literate judge will probe.
