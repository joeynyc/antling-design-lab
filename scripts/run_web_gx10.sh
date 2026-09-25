#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$project_root/jobs"
env_args=()
if [[ -f "$project_root/.env" ]]; then
  env_args=(--env-file "$project_root/.env")
fi

docker run --rm --name ming-layer-web --gpus all --ipc=host \
  "${env_args[@]}" --add-host=host.docker.internal:host-gateway \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:8765:8765 \
  -e HOME=/tmp -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -e HF_ENABLE_PARALLEL_LOADING="${MING_PARALLEL_LOADING:-false}" \
  -e HF_PARALLEL_LOADING_WORKERS="${MING_PARALLEL_WORKERS:-4}" \
  -e PYTHONPATH=/app:/upstream \
  -e MING_UPSTREAM_DIR=/upstream -e MING_MODEL_DIR=/model \
  -e MING_DESIGN_MODEL_DIR=/design-model -e MING_JOBS_DIR=/jobs \
  -e MING_IDLE_UNLOAD_SECONDS="${MING_IDLE_UNLOAD_SECONDS:-900}" \
  -e MING_ATTENTION_IMPLEMENTATION="${MING_ATTENTION_IMPLEMENTATION:-eager}" \
  -e MING_DUAL_MODEL_CACHE="${MING_DUAL_MODEL_CACHE:-true}" \
  -v "$project_root/upstream:/upstream:ro" \
  -v "$project_root/model:/model:ro" \
  -v "$project_root/design-model:/design-model:ro" \
  -v "$project_root/web:/app/web:ro" \
  -v "$project_root/resources:/app/resources:ro" \
  -v "$project_root/jobs:/jobs" \
  -w /app \
  ming-image-layer:gx10 \
  python -m uvicorn web.server:app --host 0.0.0.0 --port 8765 --workers 1
