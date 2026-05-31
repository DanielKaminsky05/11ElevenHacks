# TransitRL — The Spark Story

How to win the 15-point **"Spark Story"** sub-criterion ("can you articulate *why* this runs
better on a DGX Spark?") — grounded in what the GB10 hardware, NVIDIA's models, and the
CUDA-X libraries actually do well. Companion to [`idea-critique.md`](idea-critique.md), which
flagged the current Spark story as the weakest part of the NVIDIA section.

> **The one-sentence reframe:** the DGX Spark's strength is **not speed** — its memory
> bandwidth (273 GB/s) is ~6.5× *below* a discrete RTX 5090, so single-stream LLM decode is
> actually slow. Its strength is **capacity, CPU↔GPU memory coherence, locality, and
> compute-bound batched parallelism.** Build the story on those four, never on raw tok/s.

---

## 1. The headline story (lead with this)

> **"The entire planning copilot lives in one 128 GB coherent memory pool — and the RL
> simulation that drives it is GPU-bound, not preprocessing."**
>
> On the Spark's 128 GB unified memory, our local **Nemotron** model + its long-context KV
> cache, the multi-channel Toronto **city-grid tensor**, the **RL replay buffer**, and
> **hundreds of parallel accessibility-simulation environments** all sit in the *same* memory,
> addressable by both the Arm CPU and the Blackwell GPU with **zero PCIe copies** (NVLink-C2C
> coherence). On a 32 GB discrete GPU you must choose: load the model *or* keep the city
> resident. Here we hold both, and step thousands of sim evaluations per RL episode entirely
> on-GPU.

This is the strongest beat because it (a) maps directly onto the rubric's own example ("128 GB
unified memory to hold X and Y simultaneously"), (b) is **true and Spark-specific** — no
consumer desktop can do it, and (c) reframes the GPU as *load-bearing in the hot loop*, which
preempts the judge's "is the GPU just preprocessing?" probe.

**Say the headroom math, not "we use all 128 GB"** (the latter signals you don't understand
unified memory). Concrete: Nemotron 3 **Nano** (30B-A3B, NVFP4) uses ~27 GB, leaving ~89 GB
for context + the city tensor × N envs; Nemotron 3 **Super** (120B) uses ~94 GB, leaving ~27 GB.
([unified-memory math](https://frankdenneman.ai/posts/2026-03-23-understanding-unified-memory-dgx-spark-nemoclaw-nemotron/))

---

## 2. The four pillars (each is true on GB10; pick the ones you can demo)

### Pillar A — Capacity & coherence (*the core claim*)
- 128 GB **LPDDR5x unified memory**, coherent across the 20-core Arm CPU and the Blackwell GPU via **NVLink-C2C** (~5× PCIe Gen5). GeoDataFrames built CPU-side are read by the GPU with **no host↔VRAM copy**, so the RL/sim loop ingests fresh city state every step at memory speed. ([NVIDIA DGX Spark hardware](https://docs.nvidia.com/dgx/dgx-spark/hardware.html))
- **Why it's Spark-specific:** the full multi-channel Toronto grid × N parallel envs + a 30–120B model won't co-reside in any discrete-GPU VRAM budget.

### Pillar B — The sim *is* the RL environment, written as batched GPU tensor ops (*makes the GPU load-bearing*)
This is the answer to "is the GPU actually necessary?" Don't treat GPU work as one-time
rasterization — **run the walk-accessibility simulation itself as GPU tensor ops and step many
environments in parallel:**
- population-within-walk-buffer = a **2D convolution / windowed reduction** of the population channel against a distance kernel;
- distance-to-nearest-stop = a **multi-source distance transform**;
- equity-weighted access = an elementwise weighted reduction.
- All dense tensor ops, trivially batched over a leading `env` dimension, called **thousands of times per episode**. Workload = `N_envs × steps × kernel` → saturates the GPU, lives in unified memory, **zero per-step CPU↔GPU copies**.
- Precedent: **WarpDrive** (sim+RL fully on-GPU) hit **2.9M env-steps/s with 2000 envs, ≥100× vs CPU**. ([WarpDrive paper](https://arxiv.org/abs/2108.13976)) Implement in **CuPy/PyTorch**, or upgrade to **NVIDIA Warp** (JIT GPU kernels, zero-copy with PyTorch, official **aarch64 + CUDA-13 wheels**, DGX Spark named as supported). ([Warp](https://github.com/NVIDIA/warp))

### Pillar C — Locality / privacy / unmetered agentic loop
- The whole agent loop (goal → reward-spec JSON → 15–20 MCP tool calls → narration) runs
  **on-device**; civic/equity data never leaves the box. NVIDIA explicitly markets the Spark
  for **"smart city"** and privacy-controlled agents. ([DGX Spark product page](https://www.nvidia.com/en-us/products/workstations/dgx-spark/))
- **Cost framing:** an RL loop doing thousands of LLM tool-calls + rollouts is impractical on
  per-token cloud billing; locally it's **unmetered and private**. (Say "runs locally,
  privately, unmetered" — *not* "impossible elsewhere," which is false and easy to challenge.)

### Pillar D — Compute-bound batched throughput, not single-stream speed
- Spark scales well on **parallel/batched, FP4 Tensor-Core** work even though single-stream
  decode is slow (Llama-3.1-8B: 20→**368 tok/s** as batch 1→32). Frame RL rollout + sim as
  exactly this compute-bound regime to *sidestep* the 273 GB/s bottleneck. ([LMSYS Spark review](https://www.lmsys.org/blog/2025-10-13-nvidia-dgx-spark/))

---

## 3. The model choice that strengthens the story (and wins the Nemotron bounty)

| Model | Footprint on Spark | Why | Verdict |
|---|---|---|---|
| **Nemotron 3 Nano 30B-A3B (NVFP4)** | ~27 GB, ~75 tok/s, 1M ctx | Native tool-calling + reasoning; leaves ~89 GB for the city tensor, MCP servers, sim. | **Primary — recommended.** |
| **Nemotron 3 Super 120B-A12B (NVFP4)** | ~94 GB, ~14–19 tok/s | Stronger agentic (TauBench V2 60.5) for 15–20-tool orchestration; NVIDIA lists "1× DGX Spark" as supported. | **Stretch / demo wow** if narration latency is OK. |
| Nemotron Nano 9B v2 / Llama-Nemotron-Super-49B | small | Older gen; solid fallbacks. | Safety net only. |

Sources: [Nano blog](https://huggingface.co/blog/nvidia/nemotron-3-nano-efficient-open-intelligent-models) · [Super NVFP4 card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4)

- **The co-design angle (use this verbatim):** *"Nemotron 3 was pretrained in **NVFP4
  specifically for Blackwell**, so running it in NVFP4 on the Spark is the model and the
  machine co-designed — not a portability hack."*
- **Serve via NVIDIA NIM** (OpenAI-compatible `/v1/chat/completions`, local container, official
  "NIM-on-Spark" playbook) so the stack is NVIDIA end-to-end → directly hits the rubric's
  "uses NIMs" line and the bounty. vLLM is the fallback. ([NIM guide](https://developer.nvidia.com/blog/a-simple-guide-to-deploying-generative-ai-with-nvidia-nim/))
- **"RL on both sides" rhymes with NVIDIA's own recipe:** Nemotron itself was post-trained
  with large-scale RL; your planning agent also learns by RL. ([Nemotron](https://www.nvidia.com/en-us/ai-data-science/foundation-models/nemotron/))
- Optional high-leverage add: a tiny **NeMo LoRA** on "goal → reward-spec JSON" examples — a
  second NVIDIA component to point at, feasible in the timebox. ([NeMo Customizer](https://developer.nvidia.com/nemo-customizer))

---

## 4. Align with NVIDIA's own initiatives (reference as *peers*, don't borrow their numbers)

- **Omniverse Smart City AI Blueprint** — agents running what-if scenarios over a city to make
  operations "reactive → proactive." TransitRL is the **local, one-box cousin** focused on
  transit equity. ([blog](https://blogs.nvidia.com/blog/smart-city-ai-agents-urban-operations/))
- **cuOpt** (open-sourced, Apache-2.0) — GPU decision-optimization (VRP/LP/MILP). Stop
  placement is the classic **Maximal Covering Location Problem (MILP)**, so use cuOpt as an
  **exact-optimization baseline the RL is benchmarked against** ("RL vs. MILP for the
  non-linear equity reward"). Honest framing: cuOpt does **not** plug into the PPO/DQN loop —
  it's a comparison track, not the GPU justification. ([cuOpt](https://blogs.nvidia.com/blog/cuopt-open-source/))
- **NeMo Agent / cuOpt agent-skills blueprint** — an LLM invoking a GPU solver as a tool is
  *exactly* TransitRL's pattern; cite it to show your architecture mirrors NVIDIA's reference. ([blog](https://developer.nvidia.com/blog/optimize-supply-chain-decision-systems-using-nvidia-cuopt-agent-skills/))

---

## 5. Make the GPU pipeline real (what to actually build)

1. **Rasterize** Toronto layers once with **RAPIDS cuSpatial + cuDF** → resident multi-channel
   grid tensor. Use `quadtree_point_in_polygon` (stops/census → DA polygons/cells),
   `pairwise_point_distance` / `quadtree_point_to_nearest_linestring` (distance to nearest
   stop/street). cuSpatial PIP is reported **~100×+** over geopandas (honest mid-range; the
   10,000× headline is for huge workloads). ([cuSpatial API](https://docs.rapids.ai/api/cuspatial/stable/api_docs/spatial/) · [perf](https://medium.com/rapids-ai/acclerating-gis-data-science-with-rapids-cuspatial-and-gpus-fd012b27af0a))
2. **Walk-accessibility env in CuPy/PyTorch (or Warp kernels)**, batched over N envs, stepped
   thousands of times/episode, all in unified memory; the SB3 PPO/DQN CNN policy reads the
   tensor zero-copy. **(Pillar B — the load-bearing core.)**
3. *(Optional)* **cuOpt MILP** as the exact baseline; *(optional)* **cuGraph SSSP** for true
   walk-network isochrones — but only claim a cuGraph number if the pedestrian graph is large
   enough to actually win (small graphs can be *slower* than CPU). ([cuGraph benchmarks](https://docs.rapids.ai/api/cugraph/nightly/nx_cugraph/benchmarks/))

---

## 6. The numbers to measure and quote (one real number beats ten adjectives)

Bring a **CPU-vs-GPU scaling slide** — it directly rebuts "the GPU is just preprocessing":
- **RL throughput:** env-steps/sec (or seconds-to-converge) for CPU env vs GPU env at rising
  `N_envs` — CPU flat, GPU scaling. Target **50–100×** end-to-end (conservative vs WarpDrive ≥100×).
- **Rasterization / spatial joins:** **100×+** vs geopandas (anchor to the ~140× 1M-point PIP figure).
- **Memory headroom:** "model = X GB, leaving Y GB for the city tensor + N envs + context."
- **Live map:** iterations/sec or seconds-to-converge (justifies any "real-time" claim — never say "real-time" without a number).

---

## 7. Anti-patterns — what rings hollow to NVIDIA engineers (avoid)

- ❌ "We use the Spark because it's powerful/fast." → tie to a concrete constraint the Spark removes (memory pressure, locality, cost-of-loop).
- ❌ "Couldn't run anywhere else." → it runs in the cloud too. Say **"local, private, unmetered."**
- ❌ "We use all 128 GB." → talk **headroom after the model loads**; that's the credibility marker.
- ❌ Borrowing vanity numbers ("240× faster") for *your* app → use NVIDIA's numbers only for NVIDIA's tech; quote **your measured** numbers for TransitRL.
- ❌ Calling it a **"digital twin"** → reserved for physically-accurate OpenUSD/Omniverse worlds. Say **"accessibility simulation"** / **"live geospatial model."**
- ❌ "Physical AI" / "world foundation model" → those mean robots/AVs (Cosmos). You're **agentic AI + RL + geospatial.**
- ❌ "Real-time" / "helps underserved communities" with no metric → show the equity number your sim computes (e.g. % population brought within 400 m of a stop; Gini of access time).

---

## 8. Spark setup gotchas (validate day 1 — these can eat the weekend)

- **Everything must be CUDA 13 / sm_121**, driver 580+. CUDA-12 wheels (`libcudart.so.12`) fail to import. Use NGC containers / CUDA-13 builds. ([pitfalls thread](https://forums.developer.nvidia.com/t/dgx-spark-cuda-install-pitfalls-on-ubuntu-24-04-arm64-fixed/349881))
- **RAPIDS:** use **25.10+** (`rapids=25.10` conda meta-package is GB10-tested); older channels lack GB10/aarch64 kernels. ([thread](https://forums.developer.nvidia.com/t/rapids-cudf-preview-build-request-for-grace-blackwell-gb10-dgx-aarch64-kernels-missing/352629))
- **PyTorch:** use `nvcr.io/nvidia/pytorch:25.10+` (Blackwell build); do **not** `pip install` generic torch. Gymnasium + SB3 are pure-Python and fine.
- **Nemotron NVFP4 MoE on GB10 needs the Marlin backend** (`VLLM_NVFP4_GEMM_BACKEND=marlin` / `--moe-backend marlin`); other backends report broken. Keep an **Ollama/llama.cpp GGUF fallback** warm. ([Super card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4))
- **Warp:** official aarch64 + CUDA-13 wheels; `pip install warp-lang[examples]`.

---

## 9. Pitch script (≈40 seconds, for the demo)

> *"This runs entirely on one DGX Spark. Why does it need one? Because the whole planning
> copilot is co-resident in 128 GB of coherent memory: our local Nemotron-3 model in NVFP4 —
> the model NVIDIA pretrained for Blackwell — plus its planning context, the full Toronto
> city-grid tensor, and [N] parallel accessibility simulations, all addressable by CPU and GPU
> with zero copies. The accessibility sim isn't preprocessing — it's the RL environment,
> running as batched GPU tensor ops thousands of times per episode. On a laptop GPU we'd have
> to pick the model or the city; we hold both, the city's equity data never leaves the box, and
> the agent loop runs unmetered. Here's the CPU-vs-GPU scaling — [Y]× — and here's the map
> converging live."*

---

### Hardware quick-facts (appendix)
GB10 Grace Blackwell · 20-core Arm (10× X925 + 10× A725) · Blackwell GPU 6,144 CUDA cores, 5th-gen FP4 Tensor Cores · **128 GB LPDDR5x unified, 273 GB/s** · **~1 PFLOP FP4** · NVLink-C2C coherent CPU↔GPU · ConnectX-7 · DGX OS, NIM preinstalled · compute capability **sm_121**, CUDA 13. ([hardware docs](https://docs.nvidia.com/dgx/dgx-spark/hardware.html) · [LMSYS review](https://www.lmsys.org/blog/2025-10-13-nvidia-dgx-spark/) · [playbooks](https://github.com/NVIDIA/dgx-spark-playbooks))
