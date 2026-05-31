#!/usr/bin/env bash
# Run the TransitRL FastAPI backend wired to the local Nemotron NIM.
#
# Serves on 0.0.0.0:9001 (LAN-reachable; :9000 is taken by the 311mustangs app).
# The NIM must already be up on :8001 (backend/scripts/run_nim.sh).
#
# For a durable demo, run this detached so it survives your shell/session:
#     tmux new-session -d -s transitrl backend/scripts/run_backend.sh
#     tmux attach -t transitrl     # watch logs / Ctrl-b d to detach
#     tmux kill-session -t transitrl   # stop
set -euo pipefail
cd "$(dirname "$0")/.."

export TRANSITRL_NIM_OFFLINE=false
export TRANSITRL_NIM_BASE_URL="${TRANSITRL_NIM_BASE_URL:-http://localhost:8001/v1}"
export TRANSITRL_NIM_MODEL="${TRANSITRL_NIM_MODEL:-nvidia/nemotron-nano-9b-v2}"

exec .venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-9001}" --log-level info
