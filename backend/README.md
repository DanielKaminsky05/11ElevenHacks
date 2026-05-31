# TransitRL Backend

FastAPI service for the TransitRL planning copilot. Hosts the tool layer, the
Nemotron tool-calling loop, and the RL training stream. **Runs on the DGX Spark**
(co-located with the NIM and the GPU compute); the Next.js frontend on the laptop
calls it over the LAN.

See [FastAPI Best Practices](../docs/best-practices/fastapi.md) for conventions.

## Quick start

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows
# source .venv/bin/activate                        # macOS/Linux
pip install -e ".[dev]"
cp .env.example .env        # adjust if needed
uvicorn app.main:app --reload --port 9000
```

Then:

```bash
curl http://localhost:9000/health        # {"status":"ok","grid_loaded":false}
```

The GPU/ML stack (cudf, cuspatial, cuopt, torch, gymnasium, stable-baselines3) is
**not** in the default install — it goes only on the Spark. The app boots and the
tests pass on a plain laptop because all GPU work is stubbed for now.

## Run tests

```bash
pytest
```

## Layout

```
app/
  main.py          # app assembly: lifespan, CORS, router includes (thin)
  config.py        # pydantic-settings Settings (env: TRANSITRL_*)
  state.py         # AppState + load_city_grid (stub) — loaded once in lifespan
  dependencies.py  # injectable settings / app_state
  routers/
    health.py      # GET /health
    chat.py        # POST /chat  (agent loop — stub)
  ws/
    training.py    # WS /ws/training  (RL stream — stub)
  agent/
    nim_client.py  # httpx client for the Nemotron NIM (no openai dep)
  tools/
    registry.py    # @tool decorator + registry (no tools yet)
  schemas/
    common.py      # shared Pydantic models (BBox, ...)
tests/
  test_health.py   # boots the app without a GPU
```

## What's stubbed (next phases)

- `state.load_city_grid` — rasterize open data into the GPU-resident grid.
- `routers/chat` — drive the Nemotron tool-calling loop.
- `ws/training` — stream real RL episode metrics.
- `tools/` — register the actual tools (accessibility, equity, optimize, ...).
```
