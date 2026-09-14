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

on_error() {
  local exit_code=$?
  local line_no=${BASH_LINENO[0]:-unknown}
  echo "[PixelPilot] ERROR: bootstrap failed at line ${line_no} (exit=${exit_code})" >&2
  exit "$exit_code"
}
trap on_error ERR

echo "[PixelPilot] bootstrap started: $(date -Is)"
echo "[PixelPilot] repo=$PIXELPILOT_ROOT comfy=$COMFY_DIR ref=$COMFYUI_REF"

if [[ ! -f "$PIXELPILOT_ROOT/pyproject.toml" ]]; then
  echo "[PixelPilot] ERROR: project files not found at $PIXELPILOT_ROOT" >&2
  exit 20
fi

# A manual rerun over SSH/tmux may not inherit the container environment that
# Vast injected at creation time. Recover only the PixelPilot runtime variables
# from PID 1 without printing their values. This keeps HF/Worker tokens out of
# logs while allowing an in-place repair on the same paid instance.
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' entry; do
    key="${entry%%=*}"
    case "$key" in
      HF_TOKEN|PIXELPILOT_WORKER_TOKEN|OPEN_BUTTON_TOKEN|OPEN_BUTTON_PORT|PORTAL_CONFIG|PIXELPILOT_TRUST_PROXY|PIXELPILOT_WORKER_PORT|COMFY_PORT|COMFY_URL|COMFYUI_REF|GENERATION_MAX_BATCH|GENERATION_MAX_STEPS|DATA_DIRECTORY|PIXELPILOT_REPO_URL|PIXELPILOT_REPO_REF)
        if [[ -z "${!key:-}" ]]; then
          export "$entry"
        fi
        ;;
    esac
  done < /proc/1/environ
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "[PixelPilot] ERROR: HF_TOKEN is unavailable in shell and PID 1 environment" >&2
  exit 23
fi
if [[ -z "${PIXELPILOT_WORKER_TOKEN:-}" ]]; then
  echo "[PixelPilot] ERROR: PIXELPILOT_WORKER_TOKEN is unavailable in shell and PID 1 environment" >&2
  exit 24
fi
echo "[PixelPilot] runtime secrets recovered (values hidden)"

# Vast exposes OPEN_BUTTON_PORT (8190 by default) to a public mapped host port.
# Bind the authenticated Worker directly to that container port instead of
# relying on an optional portal/proxy process. ComfyUI itself remains localhost-only.
WORKER_BIND_PORT="${OPEN_BUTTON_PORT:-$WORKER_PORT}"

# Vast images do not all expose the interpreter under the same command. Prefer
# their managed Python environment, and only fall back to system Python through
# an isolated venv so Debian-owned packages are never modified in place.
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

if [[ "$PYTHON_BIN" == "/usr/bin/python3" || "$PYTHON_BIN" == "/usr/bin/python" ]]; then
  SYSTEM_PYTHON="$PYTHON_BIN"
  VENV_DIR="$WORKSPACE/pixelpilot-venv"
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "[PixelPilot] creating isolated venv at $VENV_DIR"
    "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
  fi
  PYTHON_BIN="$VENV_DIR/bin/python"
fi

echo "[PixelPilot] python=$PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[PixelPilot] ERROR: pip is unavailable for $PYTHON_BIN" >&2
  exit 22
fi

if [[ ! -d "$COMFY_DIR/.git" ]]; then
  echo "[PixelPilot] cloning ComfyUI..."
  git clone --filter=blob:none https://github.com/Comfy-Org/ComfyUI.git "$COMFY_DIR"
fi

echo "[PixelPilot] checking out ComfyUI ref $COMFYUI_REF"
git -C "$COMFY_DIR" fetch --depth 1 origin "$COMFYUI_REF"
git -C "$COMFY_DIR" checkout --detach FETCH_HEAD

"$PYTHON_BIN" -m pip install -U pip
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

echo "[PixelPilot] starting Worker on 0.0.0.0:$WORKER_BIND_PORT (mapped Vast port)"
cd "$PIXELPILOT_ROOT"
exec "$PYTHON_BIN" -m uvicorn pixelpilot.worker:app --host 0.0.0.0 --port "$WORKER_BIND_PORT" --log-level info
