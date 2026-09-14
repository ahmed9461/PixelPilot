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
VENV_DIR="${PIXELPILOT_VENV_DIR:-$WORKSPACE/pixelpilot-venv}"

mkdir -p "$WORKSPACE"
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'rc=$?; echo "[PixelPilot] ERROR: bootstrap failed at line $LINENO (exit=$rc)" >&2; exit $rc' ERR

echo "[PixelPilot] bootstrap started: $(date -Is)"
echo "[PixelPilot] repo=$PIXELPILOT_ROOT comfy=$COMFY_DIR ref=$COMFYUI_REF"

if [[ ! -f "$PIXELPILOT_ROOT/pyproject.toml" ]]; then
  echo "[PixelPilot] ERROR: project files not found at $PIXELPILOT_ROOT" >&2
  exit 20
fi

# Prefer an existing Vast/conda virtual environment when the image provides one.
# If the image exposes only distro-managed Python, create our own venv so pip never
# attempts to modify/uninstall Debian/Ubuntu-owned packages.
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in /venv/main/bin/python /opt/conda/bin/python python; do
    if [[ "$candidate" == */* ]]; then
      resolved="$candidate"
    else
      resolved="$(command -v "$candidate" 2>/dev/null || true)"
    fi
    if [[ -n "$resolved" && -x "$resolved" ]] && "$resolved" -m pip --version >/dev/null 2>&1; then
      PYTHON_BIN="$resolved"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  BASE_PYTHON="$(command -v python3 2>/dev/null || true)"
  if [[ -z "$BASE_PYTHON" && -x /usr/bin/python3 ]]; then
    BASE_PYTHON=/usr/bin/python3
  fi
  if [[ -z "$BASE_PYTHON" || ! -x "$BASE_PYTHON" ]]; then
    echo "[PixelPilot] ERROR: no usable Python interpreter found in Vast image" >&2
    exit 21
  fi

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "[PixelPilot] creating isolated venv at $VENV_DIR"
    rm -rf "$VENV_DIR"
    if ! "$BASE_PYTHON" -m venv "$VENV_DIR"; then
      if command -v apt-get >/dev/null 2>&1; then
        echo "[PixelPilot] python venv module missing; installing python3-venv"
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y python3-venv
        rm -rf "$VENV_DIR"
        "$BASE_PYTHON" -m venv "$VENV_DIR"
      else
        echo "[PixelPilot] ERROR: cannot create Python venv and apt-get is unavailable" >&2
        exit 22
      fi
    fi
  fi
  PYTHON_BIN="$VENV_DIR/bin/python"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[PixelPilot] ERROR: selected Python is not executable: $PYTHON_BIN" >&2
  exit 23
fi
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[PixelPilot] ERROR: pip is unavailable for $PYTHON_BIN" >&2
  exit 24
fi

echo "[PixelPilot] python=$PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"
echo "[PixelPilot] pip=$($PYTHON_BIN -m pip --version)"

if [[ ! -d "$COMFY_DIR/.git" ]]; then
  echo "[PixelPilot] cloning ComfyUI..."
  git clone --filter=blob:none https://github.com/Comfy-Org/ComfyUI.git "$COMFY_DIR"
fi

echo "[PixelPilot] checking out ComfyUI ref $COMFYUI_REF"
git -C "$COMFY_DIR" fetch --depth 1 origin "$COMFYUI_REF"
git -C "$COMFY_DIR" checkout --detach FETCH_HEAD

"$PYTHON_BIN" -m pip install -U pip setuptools wheel
"$PYTHON_BIN" -m pip install -r "$COMFY_DIR/requirements.txt"
"$PYTHON_BIN" -m pip install -e "$PIXELPILOT_ROOT" hf_xet

mkdir -p \
  "$COMFY_DIR/models/diffusion_models" \
  "$COMFY_DIR/models/text_encoders" \
  "$COMFY_DIR/models/vae" \
  "$WORKSPACE/pixelpilot-output"

export PIXELPILOT_ROOT COMFY_DIR
export WORKFLOW_PATH="${WORKFLOW_PATH:-$PIXELPILOT_ROOT/resources/workflows/flux_krea_api.json}"
"$PYTHON_BIN" "$PIXELPILOT_ROOT/scripts/download_models.py"

echo "[PixelPilot] starting ComfyUI on localhost:$COMFY_PORT"
cd "$COMFY_DIR"
"$PYTHON_BIN" main.py --listen 127.0.0.1 --port "$COMFY_PORT" >"$COMFY_LOG" 2>&1 &
COMFY_PID=$!

cleanup() {
  if kill -0 "$COMFY_PID" >/dev/null 2>&1; then
    kill "$COMFY_PID" || true
  fi
}
trap cleanup EXIT INT TERM

"$PYTHON_BIN" - <<'PY'
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
exec "$PYTHON_BIN" -m uvicorn pixelpilot.worker:app --host 127.0.0.1 --port "$WORKER_PORT" --log-level info
