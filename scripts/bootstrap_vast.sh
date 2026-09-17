#!/usr/bin/env bash
set -Eeuo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
PIXELPILOT_ROOT="${PIXELPILOT_ROOT:-$WORKSPACE/PixelPilot}"
VENV_DIR="${VENV_DIR:-$WORKSPACE/pixelpilot-vllm}"
INFERENCE_PORT="${INFERENCE_PORT:-8190}"
MODEL_ID="${MODEL_ID:-Qwen/Qwen2.5-Omni-7B}"
MODEL_DTYPE="${MODEL_DTYPE:-bfloat16}"
MODEL_MAX_LEN="${MODEL_MAX_LEN:-8192}"
MODEL_GPU_MEMORY_UTILIZATION="${MODEL_GPU_MEMORY_UTILIZATION:-0.92}"
MODEL_TENSOR_PARALLEL_SIZE="${MODEL_TENSOR_PARALLEL_SIZE:-1}"
MODEL_LIMIT_IMAGES="${MODEL_LIMIT_IMAGES:-1}"
MODEL_LIMIT_AUDIO="${MODEL_LIMIT_AUDIO:-1}"
HF_HOME="${HF_HOME:-$WORKSPACE/hf-cache}"
LOG_FILE="${LOG_FILE:-$WORKSPACE/pixelpilot-bootstrap.log}"

mkdir -p "$WORKSPACE" "$HF_HOME"
exec > >(tee -a "$LOG_FILE") 2>&1

on_error() {
  local exit_code=$?
  local line_no=${BASH_LINENO[0]:-unknown}
  echo "[PixelPilot] ERROR: bootstrap failed at line ${line_no} (exit=${exit_code})" >&2
  exit "$exit_code"
}
trap on_error ERR

echo "[PixelPilot] bootstrap started: $(date -Is)"
echo "[PixelPilot] root=$PIXELPILOT_ROOT"
echo "[PixelPilot] model=$MODEL_ID"
echo "[PixelPilot] endpoint=0.0.0.0:$INFERENCE_PORT"

if [[ ! -f "$PIXELPILOT_ROOT/pyproject.toml" ]]; then
  echo "[PixelPilot] ERROR: project files not found at $PIXELPILOT_ROOT" >&2
  exit 20
fi

if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' entry; do
    key="${entry%%=*}"
    case "$key" in
      HF_TOKEN|PIXELPILOT_INFERENCE_TOKEN|INFERENCE_PORT|MODEL_ID|MODEL_DTYPE|MODEL_MAX_LEN|MODEL_GPU_MEMORY_UTILIZATION|MODEL_TENSOR_PARALLEL_SIZE|MODEL_LIMIT_IMAGES|MODEL_LIMIT_AUDIO|HF_HOME|DATA_DIRECTORY|PIXELPILOT_REPO_URL|PIXELPILOT_REPO_REF)
        if [[ -z "${!key:-}" ]]; then export "$entry"; fi
        ;;
    esac
  done < /proc/1/environ
fi

if [[ -z "${PIXELPILOT_INFERENCE_TOKEN:-}" ]]; then
  echo "[PixelPilot] ERROR: PIXELPILOT_INFERENCE_TOKEN is unavailable" >&2
  exit 24
fi

echo "[PixelPilot] runtime environment recovered (secret values hidden)"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in /venv/main/bin/python /opt/conda/bin/python python python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "[PixelPilot] ERROR: no Python interpreter found in Vast image" >&2
  exit 21
fi

echo "[PixelPilot] base python=$PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[PixelPilot] creating venv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
PYTHON_BIN="$VENV_DIR/bin/python"

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[PixelPilot] ERROR: pip unavailable in $VENV_DIR" >&2
  exit 22
fi

if ! command -v ffmpeg >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
  echo "[PixelPilot] installing ffmpeg..."
  (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg) || echo "[PixelPilot] WARNING: ffmpeg installation failed; continuing"
fi

"$PYTHON_BIN" -m pip install -U pip wheel setuptools
"$PYTHON_BIN" -m pip install -U 'vllm>=0.8.5.post1' qwen-omni-utils hf_xet

export HF_HOME MODEL_ID
if [[ -n "${HF_TOKEN:-}" ]]; then export HF_TOKEN; fi

LIMIT_MM="{\"image\":${MODEL_LIMIT_IMAGES},\"audio\":${MODEL_LIMIT_AUDIO}}"

echo "[PixelPilot] launching Qwen2.5-Omni through vLLM"
echo "[PixelPilot] dtype=$MODEL_DTYPE max_model_len=$MODEL_MAX_LEN tp=$MODEL_TENSOR_PARALLEL_SIZE"
cd "$WORKSPACE"
exec "$VENV_DIR/bin/vllm" serve "$MODEL_ID" \
  --host 0.0.0.0 \
  --port "$INFERENCE_PORT" \
  --api-key "$PIXELPILOT_INFERENCE_TOKEN" \
  --dtype "$MODEL_DTYPE" \
  --max-model-len "$MODEL_MAX_LEN" \
  --gpu-memory-utilization "$MODEL_GPU_MEMORY_UTILIZATION" \
  --tensor-parallel-size "$MODEL_TENSOR_PARALLEL_SIZE" \
  --limit-mm-per-prompt "$LIMIT_MM"
