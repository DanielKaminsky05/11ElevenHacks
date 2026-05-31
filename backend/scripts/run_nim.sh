#!/usr/bin/env bash
# Launch the NVIDIA-Nemotron-Nano-9B-v2 NIM (the DGX Spark / GB10 build) and serve
# its OpenAI-compatible API on the host. This is the model the agent loop in
# app/routers/chat.py talks to when TRANSITRL_NIM_OFFLINE=false.
#
# Port 8000 on this box is taken by an unrelated app, so we expose the NIM on 8001.
# The NGC key (for pulling weights at runtime) is read from backend/.env.nim, which
# is gitignored — never hardcode it here.
#
# Usage:  ./scripts/run_nim.sh        # start (idempotent: replaces a prior container)
#         docker logs -f transitrl-nim   # watch it load
#         docker stop transitrl-nim      # stop
set -euo pipefail

IMAGE="nvcr.io/nim/nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark:latest"
NAME="transitrl-nim"
HOST_PORT="${TRANSITRL_NIM_HOST_PORT:-8001}"
ENV_FILE="$(dirname "$0")/../.env.nim"

if [[ -f "$ENV_FILE" ]]; then
  set -a; . "$ENV_FILE"; set +a
fi
: "${NGC_API_KEY:?NGC_API_KEY not set — put it in backend/.env.nim}"

# Persist downloaded weights across restarts so we only pay the download once.
CACHE_DIR="${HOME}/.cache/nim"
mkdir -p "$CACHE_DIR"

docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" \
  --gpus all \
  --shm-size=16g \
  -e NGC_API_KEY \
  -v "$CACHE_DIR:/opt/nim/.cache" \
  -p "${HOST_PORT}:8000" \
  "$IMAGE"

echo "Started '$NAME' → http://localhost:${HOST_PORT}/v1"
echo "First boot downloads/builds the model — watch:  docker logs -f $NAME"
echo "Ready when:  curl -s http://localhost:${HOST_PORT}/v1/models"
