#!/usr/bin/env bash
# Optional WSL launcher; keeps the 256K window and leaves VRAM for other apps.
set -euo pipefail
binary="${LLAMA_SERVER:-/opt/llama.cpp/build-master/bin/llama-server}"
model="${LOCAL_GGUF:-/mnt/d/models/qwen3.8-27b/Q4_K_M/Qwen3.8-27B-Q4_K_M.gguf}"
[[ -x "$binary" && -f "$model" ]] || { echo 'Set LLAMA_SERVER and LOCAL_GGUF to existing files.' >&2; exit 2; }
[[ -n "${CUDA_VISIBLE_DEVICES:-}" ]] || { echo 'Choose GPU UUIDs through CUDA_VISIBLE_DEVICES before starting.' >&2; exit 2; }
exec "$binary" --model "$model" --alias qwen38-local-256k \
  --host 127.0.0.1 --port 18086 --ctx-size 262144 --parallel 1 \
  --flash-attn on --cache-type-k q4_0 --cache-type-v q4_0 \
  --fit on --fit-ctx 262144 --fit-target "${LOCAL_FIT_MARGIN_MIB:-4096}" \
  --batch-size "${LOCAL_BATCH_SIZE:-2048}" --ubatch-size "${LOCAL_UBATCH_SIZE:-512}" \
  --cache-ram "${LOCAL_CACHE_RAM_MIB:-8192}" --ctx-checkpoints "${LOCAL_CONTEXT_CHECKPOINTS:-32}" \
  --jinja --reasoning-budget 0
