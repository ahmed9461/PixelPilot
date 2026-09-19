#!/usr/bin/env bash
set -Eeuo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
PIXELPILOT_ROOT="${PIXELPILOT_ROOT:-$WORKSPACE/PixelPilot}"
VENV_DIR="${VENV_DIR:-$WORKSPACE/pixelpilot-runtime}"

INFERENCE_PORT="${INFERENCE_PORT:-8190}"
VLLM_INTERNAL_PORT="${VLLM_INTERNAL_PORT:-8191}"

MODEL_ID="${MODEL_ID:-Qwen/Qwen3-VL-30B-A3B-Instruct-FP8}"
MODEL_DTYPE="${MODEL_DTYPE:-auto}"
MODEL_MAX_LEN="${MODEL_MAX_LEN:-16384}"
MODEL_GPU_MEMORY_UTILIZATION="${MODEL_GPU_MEMORY_UTILIZATION:-0.82}"
MODEL_TENSOR_PARALLEL_SIZE="${MODEL_TENSOR_PARALLEL_SIZE:-1}"
MODEL_LIMIT_IMAGES="${MODEL_LIMIT_IMAGES:-1}"
MODEL_LIMIT_VIDEOS="${MODEL_LIMIT_VIDEOS:-1}"

WHISPER_MODEL="${WHISPER_MODEL:-turbo}"
WHISPER_DEVICE="${WHISPER_DEVICE:-auto}"
WHISPER_CACHE="${WHISPER_CACHE:-$WORKSPACE/whisper-cache}"
WHISPER_MIN_FREE_VRAM_GB="${WHISPER_MIN_FREE_VRAM_GB:-6}"

HF_HOME="${HF_HOME:-$WORKSPACE/hf-cache}"
LOG_FILE="${LOG_FILE:-$WORKSPACE/pixelpilot-bootstrap.log}"
VLLM_LOG="${VLLM_LOG:-$WORKSPACE/pixelpilot-vllm.log}"
GATEWAY_LOG="${GATEWAY_LOG:-$WORKSPACE/pixelpilot-gateway.log}"

mkdir -p "$WORKSPACE" "$HF_HOME" "$WHISPER_CACHE"
exec > >(tee -a "$LOG_FILE") 2>&1

VLLM_PID=""
GATEWAY_PID=""

cleanup() {
  local code=$?
  if [[ -n "$GATEWAY_PID" ]] && kill -0 "$GATEWAY_PID" 2>/dev/null; then
    kill "$GATEWAY_PID" 2>/dev/null || true
  fi
  if [[ -n "$VLLM_PID" ]] && kill -0 "$VLLM_PID" 2>/dev/null; then
    kill "$VLLM_PID" 2>/dev/null || true
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

on_error() {
  local exit_code=$?
  local line_no=${BASH_LINENO[0]:-unknown}
  echo "[PixelPilot] ERROR: bootstrap failed at line ${line_no} (exit=${exit_code})" >&2
  if [[ -f "$VLLM_LOG" ]]; then
    echo "[PixelPilot] ---- vLLM tail ----" >&2
    tail -n 80 "$VLLM_LOG" >&2 || true
  fi
  if [[ -f "$GATEWAY_LOG" ]]; then
    echo "[PixelPilot] ---- gateway tail ----" >&2
    tail -n 80 "$GATEWAY_LOG" >&2 || true
  fi
  exit "$exit_code"
}
trap on_error ERR

echo "[PixelPilot] bootstrap started: $(date -Is)"
echo "[PixelPilot] root=$PIXELPILOT_ROOT"
echo "[PixelPilot] model=$MODEL_ID"
echo "[PixelPilot] public gateway=0.0.0.0:$INFERENCE_PORT"
echo "[PixelPilot] internal vLLM=127.0.0.1:$VLLM_INTERNAL_PORT"
echo "[PixelPilot] speech=$WHISPER_MODEL device=$WHISPER_DEVICE"

if [[ ! -f "$PIXELPILOT_ROOT/pyproject.toml" ]]; then
  echo "[PixelPilot] ERROR: project files not found at $PIXELPILOT_ROOT" >&2
  exit 20
fi

# Vast injects environment variables into PID 1. Recover the runtime values
# when onstart executes in a child shell.
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' entry; do
    key="${entry%%=*}"
    case "$key" in
      HF_TOKEN|PIXELPILOT_INFERENCE_TOKEN|INFERENCE_PORT|VLLM_INTERNAL_PORT|MODEL_ID|MODEL_DTYPE|MODEL_MAX_LEN|MODEL_GPU_MEMORY_UTILIZATION|MODEL_TENSOR_PARALLEL_SIZE|MODEL_LIMIT_IMAGES|MODEL_LIMIT_VIDEOS|WHISPER_MODEL|WHISPER_DEVICE|WHISPER_CACHE|WHISPER_MIN_FREE_VRAM_GB|HF_HOME|DATA_DIRECTORY|PIXELPILOT_REPO_URL|PIXELPILOT_REPO_REF)
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

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[PixelPilot] creating runtime venv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
PYTHON_BIN="$VENV_DIR/bin/python"

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[PixelPilot] ERROR: pip unavailable in $VENV_DIR" >&2
  exit 22
fi

if ! command -v ffmpeg >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
  echo "[PixelPilot] installing ffmpeg..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg
fi

echo "[PixelPilot] installing inference runtime..."
"$PYTHON_BIN" -m pip install -U pip wheel setuptools
"$PYTHON_BIN" -m pip install -U \
  'vllm>=0.13,<1' \
  qwen-vl-utils \
  'openai-whisper>=20250625' \
  fastapi \
  uvicorn \
  python-multipart \
  httpx \
  hf_xet

export HF_HOME MODEL_ID WHISPER_CACHE WHISPER_MODEL WHISPER_DEVICE
export VLLM_INTERNAL_PORT PIXELPILOT_INFERENCE_TOKEN WHISPER_MIN_FREE_VRAM_GB
if [[ -n "${HF_TOKEN:-}" ]]; then export HF_TOKEN; fi

# Only text/image/video reach Qwen3-VL. Audio is transcribed by Whisper first.
LIMIT_MM="{\"image\":$MODEL_LIMIT_IMAGES,\"video\":$MODEL_LIMIT_VIDEOS}"

# Clear stale processes if the same Vast instance was stopped and started.
pkill -f "vllm serve.*Qwen" 2>/dev/null || true
pkill -f "pixelpilot.inference_gateway" 2>/dev/null || true
sleep 1

echo "[PixelPilot] launching Qwen3-VL through vLLM"
echo "[PixelPilot] dtype=$MODEL_DTYPE max_model_len=$MODEL_MAX_LEN gpu_util=$MODEL_GPU_MEMORY_UTILIZATION"
"$VENV_DIR/bin/vllm" serve "$MODEL_ID" \
  --host 127.0.0.1 \
  --port "$VLLM_INTERNAL_PORT" \
  --api-key "$PIXELPILOT_INFERENCE_TOKEN" \
  --dtype "$MODEL_DTYPE" \
  --max-model-len "$MODEL_MAX_LEN" \
  --gpu-memory-utilization "$MODEL_GPU_MEMORY_UTILIZATION" \
  --tensor-parallel-size "$MODEL_TENSOR_PARALLEL_SIZE" \
  --max-num-seqs 4 \
  --limit-mm-per-prompt "$LIMIT_MM" \
  --media-io-kwargs '{"video":{"num_frames":24,"frame_recovery":true}}' \
  >"$VLLM_LOG" 2>&1 &
VLLM_PID=$!

echo "[PixelPilot] waiting for vLLM (pid=$VLLM_PID)..."
ready=0
for _ in $(seq 1 900); do
  if ! kill -0 "$VLLM_PID" 2>/dev/null; then
    echo "[PixelPilot] ERROR: vLLM exited before becoming ready" >&2
    tail -n 120 "$VLLM_LOG" >&2 || true
    exit 30
  fi
  if curl -fsS \
      -H "Authorization: Bearer $PIXELPILOT_INFERENCE_TOKEN" \
      "http://127.0.0.1:$VLLM_INTERNAL_PORT/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" != "1" ]]; then
  echo "[PixelPilot] ERROR: vLLM did not become ready in time" >&2
  exit 31
fi

echo "[PixelPilot] vLLM ready; starting Whisper + public gateway"
export PYTHONPATH="$PIXELPILOT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" -m uvicorn pixelpilot.inference_gateway:app \
  --app-dir "$PIXELPILOT_ROOT/src" \
  --host 0.0.0.0 \
  --port "$INFERENCE_PORT" \
  --log-level info \
  >"$GATEWAY_LOG" 2>&1 &
GATEWAY_PID=$!

# Treat Qwen3-VL and the gateway as one runtime. If either exits, tear down
# the other process so Vast/PixelPilot cannot report a half-alive service.
set +e
wait -n "$VLLM_PID" "$GATEWAY_PID"
child_status=$?
set -e
echo "[PixelPilot] runtime process exited (status=$child_status); shutting down peer" >&2
exit "$child_status"
