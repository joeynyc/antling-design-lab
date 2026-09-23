#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
resolution="${1:-1024}"
output_dir="$project_root/results/official-card-${resolution}"
mkdir -p "$output_dir"

docker run --rm --gpus all --ipc=host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  --user "$(id -u):$(id -g)" \
  --network none \
  -e HOME=/tmp -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -v "$project_root/upstream:/workspace:ro" \
  -v "$project_root/model:/model:ro" \
  -v "$output_dir:/results" \
  -w /workspace \
  ming-image-layer:gx10 \
  python infer.py \
    --model /model \
    --task layer-decompose \
    --input-image assets/layer_samples/card_making_input.png \
    --prompt assets/layer_samples/card_making_prompt.txt \
    --attn-implementation eager \
    --resolution "$resolution" \
    --steps 12 \
    --cfg 2.0 \
    --seed 42 \
    --dtype bfloat16 \
    --local-files-only \
    --output-dir /results
