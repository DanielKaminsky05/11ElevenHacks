# FastAPI Best Practices

Guidelines for building and maintaining the Python backend in this project. The backend runs **on the DGX Spark** (where the GPU, RAPIDS/cuOpt, the RL stack, and the Nemotron NIM all live) and is consumed by the Next.js frontend over the LAN.

## The async trap (read this first)

This is the one mistake that will hurt this project specifically, because our tools do CPU/GPU-bound work (cuSpatial rasterization, RL steps, accessibility compute).

- An `async def` endpoint runs **on the event loop**. If you call blocking/CPU-bound code inside it, the whole server freezes — every other request and WebSocket queues behind it.
- A plain `def` endpoint is automatically run by FastAPI **in a threadpool**, so blocking work there does *not* freeze the event loop. When a handler's body is synchronous and compute-heavy, just declare it `def`.
- Inside an `async def` handler, wrap blocking calls in `await run_in_threadpool(fn, ...)` (from `fastapi.concurrency`) so they don't block the loop.
- **Rule of thumb:** `async def` only when the body is genuinely `await`-ing I/O (the `httpx` call to the NIM, a DB query). Heavy synchronous compute → `def` or `run_in_threadpool`.
- The CPU/GPU is still the bottleneck — threadpooling prevents *blocking*, not contention. Long jobs (RL training) must not run inline at all; see [Long-running work](#long-running-work).

## Project Structure

- Organize by **domain/feature**, not by file type. Keep routers, schemas, and services for a feature close together rather than scattering every Pydantic model into one giant `models.py`.
- Keep an `app/` package with a thin `main.py` that only assembles the app (lifespan, middleware, router includes). No business logic in `main.py`.
- Keep tool/compute logic **transport-agnostic** — a function that computes a result must not know whether it was reached via REST, the agent loop, or MCP. Routers are thin adapters that call into services.
- Put pure helpers and the spatial/compute layer in their own modules so they're unit-testable without starting the server.

## Lifespan & shared state

- Use the `lifespan` async context manager (the `lifespan=` arg to `FastAPI(...)`), not the deprecated `@app.on_event`.
- **Load the city grid once, at startup, into the lifespan** — rasterize the open-data layers a single time and keep the tensor resident. This is the concrete realization of the "128 GB unified memory" Spark story: every request reuses the in-memory grid instead of reloading from disk.
- Store shared singletons (the grid, the loaded RL policy, the NIM client) on `app.state`, not in module globals. Access them via a dependency so they're easy to override in tests.
- Do slow startup work (model load, rasterization) in the lifespan so the first request isn't penalized — but guard it so the app still imports on a laptop without a GPU (lazy/optional GPU import).

## Configuration

- Use **`pydantic-settings`** (`BaseSettings`) for typed, validated config loaded from environment / `.env`. Misconfiguration should fail fast at startup, not at first request.
- Everything environment-specific goes through Settings: NIM base URL, model name, allowed CORS origins, grid resolution, data directory.
- Provide a committed `.env.example`; never commit real `.env`. Settings should have sensible local defaults (e.g. NIM at `localhost:8000`).
- Expose Settings via a cached dependency (`@lru_cache`) so it's constructed once and injectable.

## Schemas & validation (Pydantic v2)

- Every request and response body is a Pydantic v2 model. Let FastAPI validate inputs before they reach your code — invalid input returns a structured 422 automatically.
- Define explicit `response_model` on endpoints so outputs are validated and the OpenAPI docs are accurate.
- Keep request, response, and internal/domain models separate; don't leak internal fields out of an API by reusing one model everywhere.
- These same Pydantic models become the **tool schemas** later (`model_json_schema()` feeds the Nemotron tool-calling list), so model them carefully.

## Dependency Injection

- Use `Depends` for shared concerns: settings, the city-grid handle, the NIM client, request validation. It keeps handlers thin and makes everything mockable in tests.
- Prefer dependencies over importing singletons directly — a test can override a dependency with `app.dependency_overrides` without monkeypatching.
- Keep dependencies cheap; do expensive setup once in the lifespan and have the dependency just hand back the cached object.

## Long-running work

- RL training and large optimizations **must not** run inside a request — they take minutes. Return a job id immediately and run the work out of band.
- For fire-and-forget post-response work, use `BackgroundTasks`. For real training jobs, use a background task/worker that pushes progress to a **WebSocket** so the map animates live.
- Stream episode metrics over a WebSocket (`@app.websocket`) rather than polling. Keep the socket handler lean — it should consume from a queue the worker fills, not do compute itself.
- Make jobs cancellable and clean up on disconnect.

## CORS & networking

- The browser origin (laptop, `http://localhost:3000`) differs from the API host (the Spark), so **`CORSMiddleware` is required** — allow the frontend origin explicitly via Settings; don't hardcode.
- Avoid `allow_origins=["*"]` together with credentials; list real origins.
- Bind the server to `0.0.0.0` so the laptop can reach it over the LAN, and expose a `/health` endpoint for a quick reachability check from the frontend machine.

## Errors & logging

- Raise `HTTPException` for expected client errors; register exception handlers for domain errors so clients get consistent JSON, not a 500 with a stack trace.
- Never leak stack traces or internal paths in responses. Log them server-side instead.
- Use structured logging and include a request/job id so a streamed training run can be correlated with its logs.

## Testing

- Test the compute/service layer as plain functions — no server, no model (see [Testing Best Practices](testing.md)).
- For endpoints, use Starlette's `TestClient` / httpx `ASGITransport`; override dependencies instead of standing up real GPU/model resources.
- Mock the NIM at the `httpx` boundary; never require a live Nemotron to run the test suite.

## Code Quality

- Type-annotate everything; the framework relies on annotations and you get editor/CI checking for free.
- Pin dependencies and keep GPU-only packages (cudf, cuspatial, cuopt, torch) in a separate optional group so the app still installs and runs on a non-GPU laptop for development.
- Run `ruff`/lint and the test suite before committing.
