#!/usr/bin/env bash
set -Eeuo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
PIXELPILOT_ROOT="${PIXELPILOT_ROOT:-$WORKSPACE/PixelPilot}"
VENV_DIR="${VENV_DIR:-$WORKSPACE/pixelpilot-image-runtime}"
RUNTIME_MARKER="$VENV_DIR/.pixelpilot-runtime-version"
RUNTIME_VERSION="qwen-image-2.1-v1"

INFERENCE_PORT="${INFERENCE_PORT:-8190}"
MODEL_ID="${MODEL_ID:-Qwen/Qwen-Image-2.1}"
MODEL_DTYPE="${MODEL_DTYPE:-bfloat16}"
IMAGE_MEMORY_MODE="${IMAGE_MEMORY_MODE:-auto}"
IMAGE_FULL_GPU_MIN_VRAM_GB="${IMAGE_FULL_GPU_MIN_VRAM_GB:-48}"
IMAGE_VAE_TILING="${IMAGE_VAE_TILING:-true}"
IMAGE_VAE_SLICING="${IMAGE_VAE_SLICING:-true}"
IMAGE_MAX_REFERENCE_IMAGES="${IMAGE_MAX_REFERENCE_IMAGES:-10}"
IMAGE_MAX_UPLOAD_MB="${IMAGE_MAX_UPLOAD_MB:-25}"

HF_HOME="${HF_HOME:-$WORKSPACE/hf-cache}"
LOG_FILE="${LOG_FILE:-$WORKSPACE/pixelpilot-bootstrap.log}"
GATEWAY_LOG="${GATEWAY_LOG:-$WORKSPACE/pixelpilot-image-gateway.log}"

mkdir -p "$WORKSPACE" "$HF_HOME"
exec > >(tee -a "$LOG_FILE") 2>&1

GATEWAY_PID=""

cleanup() {
  local code=$?
  if [[ -n "$GATEWAY_PID" ]] && kill -0 "$GATEWAY_PID" 2>/dev/null; then
    kill "$GATEWAY_PID" 2>/dev/null || true
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

on_error() {
  local exit_code=$?
  local line_no=${BASH_LINENO[0]:-unknown}
  echo "[PixelPilot] ERROR: bootstrap failed at line ${line_no} (exit=${exit_code})" >&2
  if [[ -f "$GATEWAY_LOG" ]]; then
    echo "[PixelPilot] ---- gateway tail ----" >&2
    tail -n 120 "$GATEWAY_LOG" >&2 || true
  fi
  exit "$exit_code"
}
trap on_error ERR

echo "[PixelPilot] bootstrap started: $(date -Is)"
echo "[PixelPilot] root=$PIXELPILOT_ROOT"
echo "[PixelPilot] model=$MODEL_ID"
echo "[PixelPilot] public image gateway=0.0.0.0:$INFERENCE_PORT"
echo "[PixelPilot] memory mode=$IMAGE_MEMORY_MODE"

if [[ ! -f "$PIXELPILOT_ROOT/pyproject.toml" ]]; then
  echo "[PixelPilot] ERROR: project files not found at $PIXELPILOT_ROOT" >&2
  exit 20
fi

# Vast injects environment variables into PID 1. Recover them when onstart
# executes in a child shell.
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' entry; do
    key="${entry%%=*}"
    case "$key" in
      HF_TOKEN|PIXELPILOT_INFERENCE_TOKEN|INFERENCE_PORT|MODEL_ID|MODEL_DTYPE|IMAGE_MEMORY_MODE|IMAGE_FULL_GPU_MIN_VRAM_GB|IMAGE_VAE_TILING|IMAGE_VAE_SLICING|IMAGE_MAX_REFERENCE_IMAGES|IMAGE_MAX_UPLOAD_MB|HF_HOME|DATA_DIRECTORY|PIXELPILOT_REPO_URL|PIXELPILOT_REPO_REF)
        if [[ -z "${!key:-}" ]]; then export "$entry"; fi
        ;;
    esac
  done < /proc/1/environ
fi

if [[ -z "${PIXELPILOT_INFERENCE_TOKEN:-}" ]]; then
  echo "[PixelPilot] ERROR: PIXELPILOT_INFERENCE_TOKEN is unavailable" >&2
  exit 24
fi

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

if [[ -d "$VENV_DIR" ]]; then
  current_version="$(cat "$RUNTIME_MARKER" 2>/dev/null || true)"
  if [[ "$current_version" != "$RUNTIME_VERSION" ]]; then
    echo "[PixelPilot] rebuilding stale runtime venv"
    rm -rf "$VENV_DIR"
  fi
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[PixelPilot] creating runtime venv at $VENV_DIR"
  "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
  echo "$RUNTIME_VERSION" > "$RUNTIME_MARKER"
fi
PYTHON_BIN="$VENV_DIR/bin/python"

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[PixelPilot] ERROR: pip unavailable in $VENV_DIR" >&2
  exit 22
fi

echo "[PixelPilot] installing Qwen-Image runtime..."
"$PYTHON_BIN" -m pip install -U pip wheel setuptools
"$PYTHON_BIN" -m pip install -U   'transformers>=5.17.0'   accelerate   pillow   fastapi   uvicorn   python-multipart   hf_xet
"$PYTHON_BIN" -m pip install -U   'git+https://github.com/huggingface/diffusers.git'

# Reuse the CUDA-enabled torch from the Vast PyTorch image. If it is absent
# from the image, install a current PyTorch wheel as a fallback.
if ! "$PYTHON_BIN" -c 'import torch; assert torch.cuda.is_available()' >/dev/null 2>&1; then
  echo "[PixelPilot] CUDA PyTorch was not visible in the runtime; installing torch fallback"
  "$PYTHON_BIN" -m pip install -U 'torch>=2.4.0'
fi

export HF_HOME MODEL_ID MODEL_DTYPE IMAGE_MEMORY_MODE
export IMAGE_FULL_GPU_MIN_VRAM_GB IMAGE_VAE_TILING IMAGE_VAE_SLICING
export IMAGE_MAX_REFERENCE_IMAGES IMAGE_MAX_UPLOAD_MB PIXELPILOT_INFERENCE_TOKEN
if [[ -n "${HF_TOKEN:-}" ]]; then export HF_TOKEN; fi

pkill -f "pixelpilot.inference_gateway" 2>/dev/null || true
sleep 1

echo "[PixelPilot] launching Qwen-Image-2.1 gateway"
export PYTHONPATH="$PIXELPILOT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" -m uvicorn pixelpilot.inference_gateway:app   --app-dir "$PIXELPILOT_ROOT/src"   --host 0.0.0.0   --port "$INFERENCE_PORT"   --log-level info   >"$GATEWAY_LOG" 2>&1 &
GATEWAY_PID=$!

set +e
wait "$GATEWAY_PID"
child_status=$?
set -e
echo "[PixelPilot] image runtime exited (status=$child_status)" >&2
exit "$child_status"
