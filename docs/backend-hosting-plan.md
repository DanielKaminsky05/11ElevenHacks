# TransitRL — Backend Hosting Plan (ASUS Ascent GX10 / DGX Spark)

How we host the TransitRL backend on the **ASUS Ascent GX10** (`gx10-4a58`) — architecture
options, model + serving choices, the 128 GB memory budget, the problem list, and a demo-day
runbook. Synthesized from four parallel research passes (serving architecture, LLM/memory,
networking, aarch64/CUDA-13 pitfalls) + the existing [`backend/`](../backend/) scaffold.

> ⚠️ **Pending live verification.** This plan was written from research + docs; I have **not yet
> SSH'd into the box** (need the username on `gx10-4a58`). Everything in §9 "Validate on-box"
> must be confirmed live — treat version numbers as targets until checked with the smoke tests.

> **The box:** GB10 Grace Blackwell, 20-core Arm + Blackwell GPU **(sm_121)**, **128 GB
> coherent unified memory (~121 GB usable, 273 GB/s)**, CUDA 13 / driver 580+, DGX OS
> (Ubuntu 24.04 arm64), **Docker + NVIDIA Container Toolkit preinstalled**. Software-identical
> to a stock DGX Spark — all NVIDIA DGX Spark playbooks apply.

---

## 1. TL;DR — the recommendation

**Go Hybrid (containerized LLM + one app container), serve a small Nemotron on raw vLLM, run
RL in a separate process, reach it over Tailscale.**

- **Architecture:** *Hybrid (Option C).* A **vLLM container** serves Nemotron on an
  OpenAI-compatible `:8000/v1`; **one app container** (built FROM `nvcr.io/nvidia/pytorch:25.11-py3`)
  runs FastAPI + the MCP tools + the agent loop + the RL trainer; **Caddy** is the single
  entrypoint; **Tailscale** carries traffic to the laptop frontend.
- **Serving engine:** **raw vLLM, *not* NIM.** NIM's container has a confirmed
  memory-runaway bug on the GB10 unified-memory box (ignores all memory-limit params, grabs
  ~115 GB). vLLM lets us pin `--gpu-memory-utilization` and ships the Nemotron tool-call +
  reasoning parsers and guided-JSON decoding we need.
- **Model:** **NVIDIA Nemotron 3 Nano 30B-A3B (NVFP4)** — ~27–32 GB resident, leaves **~90 GB**
  for RL + the geo pipeline so it can **co-run**. (Nano-9B = lighter fallback; Super-120B =
  time-slice-only stretch.)
- **The one config that makes-or-breaks it:** GB10 is `sm_121` and the default vLLM FP4 path
  **silently fails** → you *must* force the **Marlin** backend (3 env vars, §4).
- **Biggest risk:** **unified-memory exhaustion = whole-system freeze** (no MIG, MPS unmetered).
  Mitigate with small model + explicit caps on every consumer + **`swapoff -a`**.

---

## 2. What we're hosting (components)

From [`backend/README.md`](../backend/README.md), the scaffold already matches this topology
("FastAPI runs on the Spark, co-located with the LLM; the Next.js frontend on the laptop calls
it over the LAN"). Components:

| # | Component | Stack | GPU? |
|---|---|---|---|
| 1 | LLM serving (agent brain) | Nemotron via vLLM, OpenAI-compatible | Yes |
| 2 | MCP tool server (~15–20 tools) | Python MCP SDK / FastMCP, Streamable-HTTP | No (calls 3/5) |
| 3 | API + live stream | FastAPI + uvicorn + **WebSocket** (RL episodes) | No |
| 4 | RL trainer | Gymnasium + Stable-Baselines3 + PyTorch, CNN policy | Yes |
| 5 | Geo pipeline | cuDF + custom CuPy/Warp kernels; shapely CPU fallback | Yes |
| 6 | (optional) optimizer baseline | cuOpt (MILP) — conda, separate | Yes |

---

## 3. Architecture options & trade-offs

| | (A) All-native | (B) Full containers | (C) Hybrid ✅ |
|---|---|---|---|
| What | venvs/conda + systemd | one container per concern, compose | LLM container + 1 app container + proxy |
| sm_121 build risk | **High** (pip wheel hell) | Low (NGC prebuilt) | Low |
| Dev iteration | High | Low (slow rebuilds) | **High** — app hot-reloads, LLM stays warm |
| Demo robustness | Medium | High | **High** |
| Memory control | manual | per-container, no isolation | explicit budget, vLLM capped |
| Restart/resilience | systemd | compose `restart:` | compose `restart:` + uvicorn reload |

- **(A) All-native** — fastest inner loop *if it installs*, but on `sm_121` the native pip path
  is the single biggest time-sink (CUDA-12 wheels, ptxas, NVRTC, flash-attn). Not worth the
  weekend risk except as a dev convenience inside a working container.
- **(B) Full containers** — most reproducible, but RAPIDS + PyTorch + SB3 in one image is a
  big brittle Dockerfile and slow to rebuild.
- **(C) Hybrid — recommended.** Isolates the hardest-to-build, slow-to-start, must-be-rock-solid
  piece (the LLM) so it stays warm while you hot-reload app code; RL in a separate process so
  training never blocks the WebSocket; memory explicitly budgeted by capping vLLM.

### Recommended topology (C)
```
 Browser (Next.js, laptop)                ┌──── GX10 / GB10 — 128 GB unified memory ─────────┐
        │  http/ws over Tailscale (100.x) │                                                  │
        ▼                                  │  ┌─────────┐  compose net (localhost)            │
   ┌──────────┐                            │  │  Caddy  │ / → (frontend, optional)            │
   │ frontend │──────────── Tailscale ────▶│  │  proxy  │ /api,/ws → app   :8000 internal     │
   └──────────┘                            │  └─────────┘                                     │
                                           │  ┌───────────────────────────────────────────┐  │
                                           │  │ APP container (FROM nvcr pytorch:25.11)     │  │
                                           │  │  FastAPI + MCP (Streamable-HTTP)            │  │
                                           │  │  WebSocket ← asyncio.Queue ← RL callback    │  │
                                           │  │  RL trainer = SEPARATE PROCESS              │  │
                                           │  │  cuDF + CuPy/Warp geo kernels               │  │
                                           │  │  OpenAI client ─────────────┐ (--gpus all)  │  │
                                           │  └─────────────────────────────┼─────────────┘  │
                                           │  ┌─────────────────────────────▼─────────────┐  │
                                           │  │ vLLM container  Nemotron NVFP4  :8000/v1    │  │
                                           │  │  --gpu-memory-utilization 0.5  (stays warm) │  │
                                           │  └─────────────────────────────────────────────┘ │
                                           └───────────────────────────────────────────────────┘
```

---

## 4. Serving engine: vLLM (not NIM), with the mandatory `sm_121` fix

**Why vLLM over NIM:** NIM on GB10 has a confirmed **memory-runaway bug** — the wrapper reads
the full 128 GB as "GPU memory" and ignores `NIM_GPU_MEMORY_UTILIZATION`/`--memory`/cgroups,
grabbing ~115 GB and starving RL + geo. vLLM honors `--gpu-memory-utilization`, and is the only
engine with first-class Nemotron **tool-call** (`qwen3_coder`) + **reasoning** (`nano_v3`)
parsers *and* guided-JSON decoding. (NIM/`guided_json` is still a good *fallback* if we
time-slice and aren't co-running.)

**Trade-off vs the rubric/bounty:** NIM would look more "NVIDIA-native." But serving *Nemotron*
on vLLM still fully counts for the **Nemotron bounty** ("best use of Nemotron"), and the main
rubric's "uses NIMs/NeMo" is satisfiable elsewhere (e.g. an optional NeMo LoRA). Reliability
wins — use vLLM.

**The `sm_121` footgun (mandatory):** GB10 lacks the datacenter-Blackwell FP4 tensor-core
instructions, so vLLM's default CUTLASS/FlashInfer FP4 path **silently fails / falls back to
garbage-or-slow**. Force Marlin:
```bash
export VLLM_USE_FLASHINFER_MOE_FP4=0
export VLLM_NVFP4_GEMM_BACKEND=marlin
export VLLM_TEST_FORCE_FP8_MARLIN=1
```
Use the NVIDIA Spark-tuned container `nvcr.io/nvidia/vllm:25.11-py3` (or `26.03.post1` for the
newest Nemotron-3 support) — the stock vLLM image lacks the sm_121 FP4 paths.

| Engine | Verdict |
|---|---|
| **vLLM** | ✅ **Primary** — tool-call + reasoning parsers, guided JSON, Marlin, mem control |
| SGLang | Strong fallback (good prefix-cache for many short tool turns) |
| NIM | Use only if time-slicing; memory-runaway bug makes it risky for co-run |
| TensorRT-LLM | Only via NIM; brittle engine build on sm_121 |
| Ollama / llama.cpp | ❌ Not for agents — weak structured output + poor concurrency. Dev only. |

---

## 5. Model choice

| | **Nemotron 3 Nano 30B-A3B (NVFP4)** ✅ | Nano-9B-class | Super 120B-A12B (NVFP4) |
|---|---|---|---|
| Resident | **~27–32 GB** | ~10–12 GB | ~95–110 GB |
| Headroom for RL+geo | **~90 GB (co-run)** | ~100 GB | **~0 GB (time-slice only)** |
| Decode tok/s (single) | ~50 (up to ~75 tuned) | faster | ~16–23 |
| Agentic/tool-call | Strong (trained for it) | Good | Best ceiling |
| Verdict | **Primary** | Lighter fallback | Stretch / wow, no co-run |

**Pick Nano 30B-A3B-NVFP4.** It's the agentic sweet spot that still leaves room to co-run the
RL loop and geo pipeline. Supersedes the `nvidia/llama-3.1-nemotron-70b-instruct` currently in
[`backend/.env.example`](../backend/.env.example) — update that to the Nano model and keep the
endpoint at `http://localhost:8000/v1`.

> Concurrency note: single-stream tok/s is bandwidth-limited (273 GB/s), but aggregate
> throughput scales well with concurrency — good for an agent firing many short tool-call
> turns. When co-running with RL, cap `--max-num-seqs` (≈4–16) so the LLM doesn't eat all the
> memory bandwidth.

---

## 6. The 128 GB memory budget (the crux)

Unified memory means **"GPU OOM = system OOM"** — an over-allocation can drive the box into a
swap death-spiral and hang SSH. There is **no MIG** on GB10 and **MPS is unmetered** (can't
enforce limits), so we use *soft* partitioning: cap every consumer, and `swapoff -a` so a
runaway job dies instead of bricking the machine.

**Co-run budget (Nano, recommended):**

| Consumer | Budget | How to cap |
|---|---|---|
| OS + DGX OS + CUDA contexts | ~10 GB | leave generous; **`swapoff -a`** |
| vLLM (Nemotron Nano + KV) | ~32 GB | `--gpu-memory-utilization 0.5` + `--kv-cache-memory-bytes ~12e9` |
| PyTorch RL (policy + buffer + N envs) | ~25–40 GB | `set_per_process_memory_fraction(~0.35)`, `expandable_segments:True` |
| RAPIDS cuDF working set | ~15–25 GB | RMM pool with fixed `maximum_pool_size` |
| Headroom / fragmentation | ~15–20 GB | keep slack; UMA fragments |

Monitor with **`free -h` (the "available" column)** and the community **Sparkview** tool —
**`nvidia-smi` reports `N/A` for memory on this box.**

**Co-run vs time-slice:** Nano co-runs comfortably. Choose **time-slice** (stop the LLM to
train, or vice-versa) if you use Super-120B, or if the RL training bursts need the full
273 GB/s bandwidth (co-running splits bandwidth between both).

---

## 7. Wiring details

- **FastAPI → LLM:** OpenAI SDK pointed at `http://localhost:8000/v1` (`api_key="not-used"`).
  Tool calling via standard `tools=[...]`, `tool_choice="auto"`; structured reward-spec via
  guided JSON (vLLM xgrammar / NIM `nvext.guided_json`). Keep tool JSON-schemas simple (avoid
  `minItems`/exotic keywords — xgrammar has rejected them).
- **MCP placement:** Streamable-HTTP (not stdio). Simplest: mount in the FastAPI process
  (`mcp.http_app()` sharing lifespan); if you hit the known mount-lifespan bug, run MCP as a
  separate Streamable-HTTP process on its own port.
- **RL trainer:** **separate process** (its own `python -m app.train` or service). SB3
  `BaseCallback.on_step()` → `queue.put_nowait({episode, reward, ...})` → a background asyncio
  task → `ws.send_json()`. Throttle (every N steps), drop on slow client, `task.cancel()` on
  disconnect. Never run `model.learn()` in the request/event loop. `num_workers=0` in any
  DataLoader (forking copies the whole UMA process).
- **Geo pipeline:** rasterize with **cuDF + custom CuPy/PyTorch/Warp kernels**; shapely/geopandas
  as the CPU path. (See §8 — cuSpatial is gone.)

---

## 8. Problems / risks (ranked) + mitigations

1. **Unified-memory exhaustion → whole-system freeze.** No MIG; MPS unmetered. → small model;
   cap vLLM util + KV bytes; cap torch fraction; cap RMM pool; **`swapoff -a`**; watch `free -h`.
2. **NIM memory-runaway bug on UMA** (grabs ~115 GB, ignores limits). → **use raw vLLM** with
   explicit `--gpu-memory-utilization`.
3. **`sm_121` NVFP4 silent failure.** → force **Marlin** env vars (§4); use NVIDIA's vLLM container.
4. **`sm_121` / aarch64 / CUDA-13 wheel hell** (CUDA-12 wheels, ptxas `sm_121a`, NVRTC, flash-attn).
   → **container-first** (NGC `pytorch:25.11`/`25.12`, `vllm:25.11`); ignore the `(8.0)-(12.0)`
   capability warning; use SDPA not flash-attn; `TORCH_CUDA_ARCH_LIST=12.0`.
5. **cuSpatial is archived** (last v25.04 — no CUDA-13/aarch64; `cuspatial-cu13` on PyPI is an
   empty placeholder). → do rasterization/point-in-polygon on **cuDF + custom kernels**, shapely
   CPU fallback. **cuGraph & cuOpt have no aarch64 PyPI wheels → install via conda**, in their
   own env/container. *(This corrects `spark-story.md`, `data-layer.md`, `agent-tools.md`, which
   list cuSpatial as load-bearing.)*
6. **Training blocks API/WebSocket.** → separate process + asyncio queue + cancel-on-disconnect.
7. **Venue Wi-Fi (client isolation / no mDNS / flaky uplink).** → **Tailscale** (DERP relay
   beats client isolation); offline fallback = frontend on the box + recorded video. See §10.
8. **ASUS GX10 30 W "safety-mode" power throttle** (USB-PD firmware negotiation fail; GPU capped
   ~30 W, never gets hot). → update firmware + PD "double-flash"; **check power before debugging
   software** if performance is mysteriously bad.
9. **First-run model download (10–30 min).** → pre-pull + warm the LLM the night before; mount a
   persistent cache volume; start the LLM well before the demo.
10. **WebSocket CORS/mixed-content.** → `CORSMiddleware` does **not** cover WS — validate the
    `Origin` header manually before `accept()`. https page ⇒ must use `wss://`; http page ⇒ `ws://` ok.

---

## 9. Networking / access (frontend ↔ backend)

**Primary: Tailscale mesh** (laptop ↔ GX10). NVIDIA officially documents Tailscale for DGX
Spark; it beats venue client-isolation (DERP relay), carries raw WebSockets on any port, needs
no domain/cert, and gives zero-config SSH for remote dev. Over the tailnet, serve the frontend
plain `http` and use `ws://100.x.x.x:8000/ws` — no TLS/mixed-content/CORS friction.

- **Backup #1:** named **Cloudflare Tunnel** on a domain → persistent `https`/`wss` URL (WS on
  by default) if a public/judge-facing URL is needed. Quick Tunnel (`trycloudflare`) for
  zero-setup (changing URL, 200-concurrent cap).
- **Backup #2 (network dead):** host the **frontend on the GX10** (single origin, no CORS) over
  Ethernet/Tailscale, plus a **recorded video** as the final fallback.
- **Avoid:** ngrok free (2-hr session cap); Tailscale Funnel for the streaming WS (idle-drop bug).

```python
# FastAPI: CORS for HTTP + manual Origin check for WS (CORSMiddleware ignores WS)
ALLOWED = ["http://localhost:3000", "http://100.x.x.x:3000"]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

@app.websocket("/ws/training")
async def ws_training(ws: WebSocket):
    if ws.headers.get("origin") not in ALLOWED:
        await ws.close(code=1008); return
    await ws.accept()
```

---

## 10. Validate on-box (the first-2-hours smoke test — run once I'm SSH'd in)

```bash
# identity
nvidia-smi                 # expect driver 580.x, CUDA 13.x, "NVIDIA GB10"
uname -m                   # aarch64
free -h                    # unified memory; watch "available"
swapon --show              # want EMPTY → run: sudo swapoff -a

# container GPU access (toolkit preinstalled)
docker run --rm --gpus all nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04 nvidia-smi

# torch sees GPU (sm_121 warning is OK)
python -c "import torch;print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
python -c "import torch;a=torch.randn(4096,4096,device='cuda');print((a@a).sum().item())"

# SB3 + Gymnasium 1 step on GPU
python -c "from stable_baselines3 import PPO;PPO('MlpPolicy','CartPole-v1',device='cuda').learn(256);print('SB3 OK')"

# cuDF on GPU
python -c "import cudf;print(cudf.Series([1,2,3]).sum())"   # 6
# geo CPU fallback
python -c "import geopandas,shapely,pyproj,rasterio;print('geo OK')"

# LLM endpoint (after vLLM container is up, Marlin env set)
curl -s http://localhost:8000/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"<nemotron-nano>","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
```
Also to check live: installed CUDA/driver/DGX-OS versions, firmware (the 30 W throttle), free
disk for model weights, whether any NIM/vLLM is already running, and `nvidia-ctk --version`.

---

## 11. Runbook

**Day before (once):**
```bash
echo "$NGC_API_KEY" | docker login nvcr.io -u '$oauthtoken' --password-stdin
docker pull nvcr.io/nvidia/vllm:25.11-py3
docker pull nvcr.io/nvidia/pytorch:25.11-py3
sudo swapoff -a
# warm the Nemotron weights once so demo start is fast
```

**`docker-compose.yml` (sketch):**
```yaml
services:
  llm:
    image: nvcr.io/nvidia/vllm:25.11-py3
    environment:
      - VLLM_USE_FLASHINFER_MOE_FP4=0
      - VLLM_NVFP4_GEMM_BACKEND=marlin
      - VLLM_TEST_FORCE_FP8_MARLIN=1
    command: >
      vllm serve nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4
      --quantization modelopt_fp4 --gpu-memory-utilization 0.5 --max-num-seqs 8
      --kv-cache-dtype fp8 --enable-auto-tool-choice --tool-call-parser qwen3_coder
      --trust-remote-code --port 8000
    gpus: all
    ipc: host
    ulimits: { memlock: -1, stack: 67108864 }
    volumes: ["~/.cache/huggingface:/root/.cache/huggingface"]
    restart: unless-stopped
  app:                       # FROM nvcr.io/nvidia/pytorch:25.11-py3 + fastapi,mcp,sb3,gymnasium,cudf
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
    environment: [ "TRANSITRL_NIM_BASE_URL=http://llm:8000/v1" ]
    gpus: all
    ipc: host
    ulimits: { memlock: -1, stack: 67108864 }
    volumes: ["./backend:/workspace"]
    depends_on: [llm]
    restart: unless-stopped
  proxy:
    image: caddy:2
    ports: ["443:443","80:80"]
    volumes: ["./Caddyfile:/etc/caddy/Caddyfile"]
    depends_on: [app]
```
Container flags that matter on GB10: `--gpus all`, `--ipc=host` (default 64 MB shm too small),
`--ulimit memlock=-1`, `--ulimit stack=67108864`.

**Demo checklist:** pre-warm model + run one RL episode off-camera · `GET /health` from the
laptop · confirm WS streams one episode end-to-end · Tailscale up on both · recorded fallback ready.

---

## 12. Open decisions (need your input / on-box check)
- **Co-run vs time-slice** — defaults to co-run with Nano; confirm once we see real RL memory use.
- **RAPIDS in the app container vs its own** — try in-app first; split out if the RAPIDS↔torch
  toolchain won't co-build.
- **cuOpt baseline** — include only if time allows (conda, separate container).
- **Frontend location** — laptop over Tailscale (default) vs on-box (offline-proof).

---

### Sources
vLLM Nemotron/Marlin: vllm recipes + blog.vllm.ai · NVIDIA "Marlin Fix NVFP4 sm_121" forum ·
NIM memory-runaway forum thread · Frank Denneman unified-memory deep-dive · dgx-spark-playbooks
(NIM/vLLM/CUDA-X/Tailscale) · RAPIDS install + cuSpatial archived repo · natolambert/dgx-spark-setup
· martimramos/dgx-spark-ml-guide · NVIDIA DGX Spark container-runtime/first-boot docs · ASUS GX10
firmware + 30 W-throttle forum threads · FastMCP transports · FastAPI CORS/WebSocket docs ·
Tailscale + Cloudflare Tunnel docs. (Full URLs in the four research reports.)
