#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$project_root/jobs"

docker run --rm --name ming-layer-web --gpus all --ipc=host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:8765:8765 \
  -e HOME=/tmp -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -e PYTHONPATH=/app:/upstream \
  -e MING_UPSTREAM_DIR=/upstream -e MING_MODEL_DIR=/model -e MING_JOBS_DIR=/jobs \
  -e MING_IDLE_UNLOAD_SECONDS=900 \
  -v "$project_root/upstream:/upstream:ro" \
  -v "$project_root/model:/model:ro" \
  -v "$project_root/web:/app/web:ro" \
  -v "$project_root/jobs:/jobs" \
  -w /app \
  ming-image-layer:gx10 \
  python -m uvicorn web.server:app --host 0.0.0.0 --port 8765 --workers 1
