#!/usr/bin/env bash
set -Eeuo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
PIXELPILOT_ROOT="${PIXELPILOT_ROOT:-$WORKSPACE/PixelPilot}"
COMFY_DIR="${COMFY_DIR:-$WORKSPACE/ComfyUI}"
COMFY_PORT="${COMFY_PORT:-8188}"
WORKER_PORT="${PIXELPILOT_WORKER_PORT:-18190}"
COMFYUI_REF="${COMFYUI_REF:-v0.35.0}"
LOG_FILE="${LOG_FILE:-$WORKSPACE/pixelpilot-bootstrap.log}"
COMFY_LOG="${COMFY_LOG:-$WORKSPACE/comfyui.log}"

mkdir -p "$WORKSPACE"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[PixelPilot] bootstrap started: $(date -Is)"
echo "[PixelPilot] repo=$PIXELPILOT_ROOT comfy=$COMFY_DIR ref=$COMFYUI_REF"

if [[ ! -f "$PIXELPILOT_ROOT/pyproject.toml" ]]; then
  echo "[PixelPilot] ERROR: project files not found at $PIXELPILOT_ROOT" >&2
  exit 20
fi

if [[ ! -d "$COMFY_DIR/.git" ]]; then
  echo "[PixelPilot] cloning ComfyUI..."
  git clone --filter=blob:none https://github.com/Comfy-Org/ComfyUI.git "$COMFY_DIR"
fi

echo "[PixelPilot] checking out ComfyUI ref $COMFYUI_REF"
git -C "$COMFY_DIR" fetch --depth 1 origin "$COMFYUI_REF"
git -C "$COMFY_DIR" checkout --detach FETCH_HEAD

python -m pip install -U pip
python -m pip install -r "$COMFY_DIR/requirements.txt"
python -m pip install -e "$PIXELPILOT_ROOT" hf_xet

mkdir -p \
  "$COMFY_DIR/models/diffusion_models" \
  "$COMFY_DIR/models/text_encoders" \
  "$COMFY_DIR/models/vae" \
  "$WORKSPACE/pixelpilot-output"

export PIXELPILOT_ROOT COMFY_DIR
export WORKFLOW_PATH="${WORKFLOW_PATH:-$PIXELPILOT_ROOT/resources/workflows/flux_krea_api.json}"
python "$PIXELPILOT_ROOT/scripts/download_models.py"

echo "[PixelPilot] starting ComfyUI on localhost:$COMFY_PORT"
cd "$COMFY_DIR"
python main.py --listen 127.0.0.1 --port "$COMFY_PORT" >"$COMFY_LOG" 2>&1 &
COMFY_PID=$!

cleanup() {
  if kill -0 "$COMFY_PID" >/dev/null 2>&1; then
    kill "$COMFY_PID" || true
  fi
}
trap cleanup EXIT INT TERM

python - <<'PY'
import os, sys, time, urllib.request
port = int(os.environ.get('COMFY_PORT', '8188'))
timeout = int(os.environ.get('COMFY_READY_TIMEOUT_SECONDS', '1200'))
url = f'http://127.0.0.1:{port}/system_stats'
deadline = time.monotonic() + timeout
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            if 200 <= r.status < 300:
                print('[PixelPilot] ComfyUI API is ready')
                raise SystemExit(0)
    except Exception:
        time.sleep(3)
print(f'[PixelPilot] ERROR: ComfyUI not ready after {timeout}s', file=sys.stderr)
raise SystemExit(30)
PY

echo "[PixelPilot] starting Worker on localhost:$WORKER_PORT"
cd "$PIXELPILOT_ROOT"
exec python -m uvicorn pixelpilot.worker:app --host 127.0.0.1 --port "$WORKER_PORT" --log-level info
