# TransitRL — Backend Hosting Plan (ASUS Ascent GX10 / DGX Spark)

How we host the TransitRL backend on the **ASUS Ascent GX10** (`gx10-4a58`). **Updated with
live on-box findings** (SSH'd in 2026-05-31) — model choice, serving stack, the memory budget,
the problem list, networking, and a runbook. Synthesized from four research passes + the
existing [`backend/`](../backend/) scaffold + **direct inspection of the running machine.**

> ✅ **Verified live (2026-05-31).** Connected as `asus@gx10-4a58` over Tailscale. The box is
> **already up and serving** — and importantly it's **shared/multi-tenant** (other agents +
> an Ollama stack are running on it). Key numbers below are measured, not assumed.

---

## 0. What's actually on the box (verified)

| Property | Value (measured) |
|---|---|
| Host / user | `gx10-4a58` / `asus` · reachable via **Tailscale `100.81.100.96`** (LAN `10.10.53.58`) |
| OS / arch | Ubuntu 24.04.4 LTS, **aarch64** |
| GPU / driver / CUDA | **NVIDIA GB10**, driver **580.142**, **CUDA 13.0** |
| Unified memory | **121 GiB** total · idle baseline ~6 GiB used |
| MIG | **Not Supported** (confirmed on-box) |
| Power | idle **12 W / 39 °C** — **not** power-throttled (the ASUS 30 W bug is *not* present on this unit) ✅ |
| Disk | 916 GB, **592 GB free** (plenty for model weights) |
| Containers | Docker **29.2.1**, NVIDIA Container Toolkit **1.19.0** (preinstalled) |
| **LLM stack in place** | **Ollama 0.24.0**, OpenAI-compatible at **`http://localhost:11434/v1`** |
| Ports already in use | `11434` (Ollama), `9000` (a uvicorn → `{"status":"ok"}`), `8000` (HTTP, 404), `8080` (loopback + docker bridge) |
| Other tenants | an `openclaw` sandbox container + multiple `claude`/`node`/`uvicorn` processes — **this box is shared** |

**Implication:** we are a *guest* on a running machine. Don't assume exclusive use of memory or
ports, and coordinate before changing global state (swap, killing processes, loading big models).

---

## 1. TL;DR — the recommendation (revised after on-box testing)

**Build the agent loop directly on the Ollama stack that's already running, using
`nemotron3:33b` — it's validated, fast, and fits the co-run budget. Keep vLLM as an optional
hardening step, not a prerequisite.**

- **Serving:** **Ollama** (already running, OpenAI-compatible at `:11434/v1`). Our earlier
  research warned "Ollama is weak for agents" — **on-box testing disproved that for our case**
  (see §4): tool-calling returned correct, valid-JSON calls 3/3. So we **skip the vLLM
  migration** unless we later need NVFP4 throughput or hard guided-JSON guarantees.
- **Model:** **`nemotron3:33b`** (NVIDIA Nemotron 3, ~27 GB on disk / ~32 GB loaded, 128K ctx).
  Chosen, loaded, and pinned. Hits the **Nemotron bounty**, and leaves **~79 GB** for the RL
  loop + geo pipeline → genuine co-run.
- **Measured speed:** **~67–81 tok/s decode, ~2,550 tok/s prefill**; a tool-call turn is
  **~0.8–1.0 s with thinking off**, 4.8 s with thinking on.
- **Architecture:** **Hybrid** — Ollama serves the model; **one app container** (FROM
  `nvcr.io/nvidia/pytorch:25.11-py3`) runs FastAPI + MCP + the agent loop + the RL trainer
  (RL in a separate process); reach it over **Tailscale** (already set up).
- **Biggest risks now:** (1) **shared-box memory contention** — other tenants can eat our
  ~79 GB headroom; (2) **port conflicts** (`:9000`, `:8000`, `:11434` already taken);
  (3) **swap is ON** and disabling it affects other tenants.

---

## 2. What we're hosting (components)

[`backend/README.md`](../backend/README.md) already matches the intended topology. Components:

| # | Component | Stack | GPU? | Status on box |
|---|---|---|---|---|
| 1 | LLM serving (agent brain) | **Ollama → `nemotron3:33b`**, OpenAI API | Yes | ✅ running + validated |
| 2 | MCP tool server (~15–20 tools) | Python MCP SDK / FastMCP, Streamable-HTTP | No | to build |
| 3 | API + live stream | FastAPI + uvicorn + **WebSocket** (RL episodes) | No | scaffolded |
| 4 | RL trainer | Gymnasium + Stable-Baselines3 + PyTorch, CNN policy | Yes | to build |
| 5 | Geo pipeline | cuDF + custom CuPy/Warp kernels; shapely CPU fallback | Yes | to build |
| 6 | (optional) optimizer baseline | cuOpt (MILP) — conda, separate | Yes | optional |

---

## 3. Architecture options & trade-offs

| | (A) All-native | (B) Full containers | (C) Hybrid ✅ |
|---|---|---|---|
| sm_121 build risk | High (pip wheel hell) | Low (NGC prebuilt) | Low |
| Dev iteration | High *if it installs* | Low (slow rebuilds) | **High** — app reloads, LLM stays warm |
| Demo robustness | Medium | High | **High** |
| Memory control | manual | per-container, no isolation | explicit budget |
| Fit to *this* box | — | — | **Best — Ollama already provides the LLM tier** |

**Recommended: Hybrid (C).** The box already gives us tier 1 (Ollama). We add **one app
container** for FastAPI + MCP + RL (RL as a separate process so training never blocks the
WebSocket), talking to Ollama over `localhost:11434`. All-native is risky on `sm_121`; full
containers are slow to iterate.

```
 Browser (Next.js, laptop)            ┌──── GX10 / GB10 — 121 GiB unified (SHARED box) ───────┐
        │ http/ws over Tailscale      │                                                       │
        ▼  (100.81.100.96)            │  ┌─────────┐                                          │
   ┌──────────┐                       │  │  Caddy  │ /api,/ws → app   (pick a FREE port)      │
   │ frontend │───── Tailscale ──────▶│  └─────────┘                                          │
   └──────────┘                       │  ┌───────────────────────────────────────────────┐   │
                                      │  │ APP container (FROM nvcr pytorch:25.11)         │   │
                                      │  │  FastAPI + MCP (Streamable-HTTP)                │   │
                                      │  │  WebSocket ← asyncio.Queue ← RL callback        │   │
                                      │  │  RL trainer = SEPARATE PROCESS                  │   │
                                      │  │  cuDF + CuPy/Warp geo kernels                   │   │
                                      │  │  OpenAI client ───────────────┐                 │   │
                                      │  └───────────────────────────────┼─────────────────┘   │
                                      │  ┌───────────────────────────────▼─────────────────┐   │
                                      │  │ Ollama (ALREADY RUNNING)  :11434/v1               │   │
                                      │  │   nemotron3:33b  pinned (keep_alive=-1)           │   │
                                      │  └───────────────────────────────────────────────────┘ │
                                      │  [other tenants: openclaw sandbox, claude agents]      │
                                      └─────────────────────────────────────────────────────────┘
```

---

## 4. Serving engine & model — validated on-box

### Engine: Ollama (in place) — and it's good enough for our agent
The research ranked vLLM > Ollama for agentic work, but **the deciding factor is what's actually
running and whether it passes our tests.** It does. Live tool-calling test (OpenAI endpoint,
`temperature=0`, two TransitRL tools):

| Test | Latency | Result |
|---|---|---|
| equity query, `/no_think` | **0.8 s** | `equity_gap_report({"region":"Scarborough"})` — valid JSON ✅ |
| equity query, thinking ON | 4.8 s | same correct call ✅ |
| accessibility query, `/no_think` | **1.0 s** | `compute_accessibility({"area":"Malvern","mode":"walk","threshold_m":400})` ✅ |

It picked the right tool every time and **inferred unstated args from natural language**
(`"on foot"`→`walk`, `"within 400m"`→`threshold_m:400`). Conclusion: **build on Ollama now.**

- **When to add vLLM later (optional):** if we need NVFP4 throughput, hard JSON-schema-guided
  decoding, or higher concurrency. Then serve the same Nemotron via `nvcr.io/nvidia/vllm:25.11-py3`
  with the mandatory `sm_121` Marlin env vars (`VLLM_NVFP4_GEMM_BACKEND=marlin`,
  `VLLM_USE_FLASHINFER_MOE_FP4=0`, `VLLM_TEST_FORCE_FP8_MARLIN=1`).
- **Avoid NIM here:** confirmed memory-runaway bug on GB10 UMA (grabs ~115 GB, ignores limits).

### Model: `nemotron3:33b` (chosen, loaded, pinned)
Installed models on the box: `nemotron3:33b` (27 GB), `nemotron-3-super:latest` (86 GB),
`qwen3.6:35b` (23 GB), `gemma4:26b` (17 GB), `llama3.2-vision:11b` (7.8 GB).

| Candidate | Footprint | Verdict |
|---|---|---|
| **`nemotron3:33b`** | ~32 GB loaded, 128K ctx | ✅ **chosen** — agentic + Nemotron bounty + co-run headroom |
| `nemotron-3-super` (120B) | ~86 GB | reasoning ceiling, but **no co-run** (time-slice only) |
| `qwen3.6:35b` | ~23 GB | strong tool-caller **fallback**, but forfeits the bounty |
| `gemma4` / `llama3.2-vision` | 17 / 7.8 GB | no bounty / vision side-tool only |

**Measured performance (`nemotron3:33b`, warm):** decode **67–81 tok/s**, prefill
**~2,550 tok/s** (4,927-token prompt in 1.9 s). → a real agent turn ≈ a few seconds; a 5–8-tool
plan ≈ 15–40 s (prefix caching helps repeats). Notably *faster* than the research's ~50 tok/s
estimate because Ollama runs it as GGUF Q4 (lighter than NVFP4), pinned warm.

**Latency policy:** **thinking OFF (`/no_think`) for tool-selection + `parse_goal`** (~0.8–1 s);
**thinking ON for `explain_result`/`generate_brief`** (reasoning adds value).

**Backend wiring:** point [`backend/.env`](../backend/.env.example) at the live endpoint —
`TRANSITRL_NIM_BASE_URL=http://localhost:11434/v1`, `TRANSITRL_NIM_MODEL=nemotron3:33b`
(replaces the stale `nvidia/llama-3.1-nemotron-70b-instruct`). Note context loaded at **131072**;
raise explicitly if we want the full 256K.

---

## 5. The memory budget (real numbers)

Measured: **121 GiB** total. With `nemotron3:33b` pinned: **~42 GiB used, ~79 GiB available.**
With it unloaded: ~6 GiB used. So the model holds ~32 GiB and we have ~79 GiB working room —
**but on a shared box, other tenants' jobs come out of that 79 GiB.**

| Consumer | Budget (co-run) | Cap |
|---|---|---|
| OS + other tenants (Ollama + agents) | ~42 GiB (incl. our model) | (shared — monitor) |
| PyTorch RL (policy + buffer + N envs) | ~25–35 GiB | `set_per_process_memory_fraction`, `expandable_segments:True` |
| RAPIDS cuDF working set | ~15–25 GiB | RMM pool with fixed `maximum_pool_size` |
| Headroom / fragmentation | ~10–15 GiB | keep slack |

- **No MIG / unmetered MPS** (confirmed) → soft caps only; cap every consumer we control.
- **Monitor with `free -h` ("available")** — `nvidia-smi` shows `N/A` for memory on this box.
- **Swap is ON (16 GiB).** Research recommends `swapoff -a` to avoid a UMA death-spiral — **but
  this is a shared box; do NOT disable swap unilaterally.** Instead cap our own processes
  tightly and coordinate before touching swap.

---

## 6. Wiring details

- **FastAPI → LLM:** OpenAI SDK / httpx → `http://localhost:11434/v1`, model `nemotron3:33b`,
  `tools=[...]`, `tool_choice="auto"`; prepend `/no_think` for tool/JSON steps.
- **MCP:** Streamable-HTTP. Mount in the FastAPI process (`mcp.http_app()` sharing lifespan); if
  the mount-lifespan bug bites, run MCP as a separate Streamable-HTTP process on its own port.
- **RL trainer:** **separate process**. SB3 `BaseCallback.on_step()` → `queue.put_nowait(...)`
  → background asyncio task → `ws.send_json()`. Throttle; drop on slow client; cancel on
  disconnect. `num_workers=0` in DataLoaders (forking copies the whole UMA process).
- **Geo pipeline:** cuDF + custom CuPy/PyTorch/Warp kernels; shapely/geopandas CPU fallback.
  **cuSpatial is archived** (no CUDA-13/aarch64) — do not depend on it; **cuGraph/cuOpt via
  conda**, not pip.

---

## 7. Problems / risks (ranked) — updated against the live box

1. **Shared-box memory contention (NEW, now #1).** Our ~79 GiB headroom shrinks when other
   tenants load models / run jobs. → cap our processes; `free -h` before launching RL; agree a
   memory budget with whoever else uses the box; consider time-slicing heavy RL.
2. **Port conflicts (NEW).** `:9000`, `:8000`, `:11434`, `:8080` already in use (and a uvicorn
   already answers on `:9000`). → bind our API to a **free** port (e.g. `:9100`) and check
   `ss -ltn` first; don't assume the README's `:9000`.
3. **Swap is ON + UMA OOM can freeze the box.** → cap our own allocations; **coordinate** before
   `swapoff -a` (it affects co-tenants).
4. **`sm_121` / aarch64 / CUDA-13 wheel hell** for our RL/geo container. → **container-first**
   (`nvcr.io/nvidia/pytorch:25.11`); ignore the `(8.0)-(12.0)` warning; SDPA not flash-attn.
5. **cuSpatial archived** → cuDF + custom kernels; cuGraph/cuOpt via conda.
6. **Training blocks API/WebSocket** → separate process + asyncio queue.
7. **Venue Wi-Fi** → **Tailscale already set up** (`100.81.100.96`) beats client-isolation;
   offline fallback = frontend on the box + recorded video.
8. **First-run model pulls** → not an issue for `nemotron3:33b` (already local + pinned); applies
   only if we add models.
9. **WebSocket CORS/mixed-content** → `CORSMiddleware` doesn't cover WS; validate `Origin`
   manually; `wss` if the page is `https`.
10. **~~ASUS 30 W power throttle~~** → **verified NOT present on this unit** (12 W idle, normal). ✅

---

## 8. Networking / access — Tailscale is live

**Primary (already working): Tailscale.** The box is on Tailscale at **`100.81.100.96`**; I'm
SSH'd in over it as `asus` with key auth. The laptop frontend talks to the box at
`http://100.81.100.96:<port>` / `ws://100.81.100.96:<port>/ws` — plain `http`/`ws`, so **no
TLS/mixed-content/CORS friction** (set FastAPI `allow_origins` to the laptop origin + manual WS
`Origin` check). Backups: named Cloudflare Tunnel (persistent `wss`) for a public URL;
frontend-on-box + recorded video if the network dies. Avoid ngrok free / Tailscale Funnel for WS.

---

## 9. On-box validation — status

| Check | Result |
|---|---|
| SSH (Tailscale, key auth) | ✅ `asus@gx10-4a58` |
| GPU / driver / CUDA | ✅ GB10 / 580.142 / 13.0 |
| Docker + NVIDIA toolkit | ✅ 29.2.1 / 1.19.0 |
| Ollama endpoint | ✅ `:11434/v1`, `nemotron3:33b` pinned |
| Tool-calling | ✅ 3/3 valid JSON calls |
| Speed | ✅ 67–81 tok/s decode, ~2,550 tok/s prefill |
| Memory headroom | ✅ ~79 GiB free with model loaded |
| **Still to validate** | PyTorch+SB3 GPU step · cuDF on GPU · our app container build · a free API port · CORS/WS from the laptop |

Remaining smoke tests to run when we stand up the app container:
```bash
docker run --rm --gpus all nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04 nvidia-smi
python -c "import torch;print(torch.cuda.get_device_name(0))"   # expect NVIDIA GB10
python -c "from stable_baselines3 import PPO;PPO('MlpPolicy','CartPole-v1',device='cuda').learn(256)"
python -c "import cudf;print(cudf.Series([1,2,3]).sum())"
ss -ltn | grep -E ':9000|:9100'   # pick a free API port
```

---

## 10. Runbook

**LLM tier — already done:**
```bash
# nemotron3:33b is loaded & pinned (keep_alive=-1). To re-pin after a restart:
curl -s http://localhost:11434/api/generate \
  -d '{"model":"nemotron3:33b","prompt":"ready","stream":false,"keep_alive":-1}'
ollama ps    # confirm it's resident (~32 GB, 100% GPU)
```

**App tier (to build):** one container FROM `nvcr.io/nvidia/pytorch:25.11-py3` adding
`fastapi uvicorn websockets "mcp[cli]" gymnasium` + `stable-baselines3 --no-deps` + `cudf-cu13`;
GPU flags `--gpus all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864`; bind FastAPI to a
**free** port; env `TRANSITRL_NIM_BASE_URL=http://host.docker.internal:11434/v1` (or the host IP),
`TRANSITRL_NIM_MODEL=nemotron3:33b`; run the RL trainer as a separate process.

**Demo checklist:** `nemotron3:33b` pinned + warm · `free -h` shows comfortable headroom ·
API `/health` from the laptop over Tailscale · WS streams one episode · recorded fallback ready.

---

## 11. Open decisions / next steps
- **Pick a free API port** (`:9000` is taken — likely `:9100`); update `backend/.env`.
- **Investigate the existing `:9000` uvicorn** — is it an older TransitRL instance from another
  machine? Reuse or replace, don't blindly collide.
- **Agree a shared-box memory budget** with the other tenants before running heavy RL.
- **Co-run vs time-slice** — co-run is fine now (~79 GiB free); re-check once RL memory is real.
- **vLLM hardening** — only if Ollama's structured output proves insufficient at scale.

---

### Sources
On-box: direct SSH inspection of `gx10-4a58` (2026-05-31) — `nvidia-smi`, `free -h`, `ollama
list/ps`, OpenAI-endpoint tool-calling + timing tests. Research: vLLM Nemotron/Marlin docs ·
NIM memory-runaway forum thread · Frank Denneman unified-memory deep-dive · dgx-spark-playbooks ·
RAPIDS install + cuSpatial-archived repo · Tailscale/Cloudflare docs · FastMCP/FastAPI docs.
(Full URLs in the four research reports.)
