from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


PROFILE = {
    "VAST_DISK_GB": "100",
    "VAST_MIN_GPU_RAM_GB": "48",
    "VAST_MAX_PRICE_USD_HOUR": "0.50",
    "VAST_MIN_INET_DOWN_MBPS": "100",
    "MODEL_ID": "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8",
    "MODEL_DTYPE": "auto",
    "MODEL_MAX_LEN": "16384",
    "MODEL_MAX_OUTPUT_TOKENS": "2048",
    "MODEL_GPU_MEMORY_UTILIZATION": "0.82",
    "MODEL_TENSOR_PARALLEL_SIZE": "1",
    "MODEL_LIMIT_IMAGES": "1",
    "MODEL_LIMIT_AUDIO": "1",
    "MODEL_LIMIT_VIDEOS": "1",
    "WHISPER_MODEL": "turbo",
    "WHISPER_DEVICE": "auto",
    "INFERENCE_PORT": "8190",
    "VLLM_INTERNAL_PORT": "8191",
    "INFERENCE_USE_HTTPS": "false",
    "INFERENCE_VERIFY_TLS": "false",
    "INFERENCE_REQUEST_TIMEOUT_SECONDS": "600",
    "INFERENCE_READY_TIMEOUT_SECONDS": "1800",
    "PROVISION_POLL_SECONDS": "5",
}


def update_env_text(text: str) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        if "=" in line and not stripped.startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in PROFILE:
                output.append(f"{key}={PROFILE[key]}")
                seen.add(key)
                continue
        output.append(line)

    missing = [key for key in PROFILE if key not in seen]
    if missing:
        if output and output[-1] != "":
            output.append("")
        output.append("# PixelPilot Qwen3-VL 30B FP8 + Whisper profile")
        output.extend(f"{key}={PROFILE[key]}" for key in missing)

    return "\n".join(output).rstrip() + "\n"


def migrate(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.before_qwen3_vl_{stamp}.bak")
    shutil.copy2(path, backup)

    original = path.read_text(encoding="utf-8")
    path.write_text(update_env_text(original), encoding="utf-8")
    return backup


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Switch an existing PixelPilot .env to Qwen3-VL 30B FP8 + Whisper without touching secrets."
    )
    parser.add_argument("--env", type=Path, default=root / ".env")
    args = parser.parse_args()

    backup = migrate(args.env)
    print(f"Updated: {args.env}")
    print(f"Backup:  {backup}")
    print("Profile: Qwen3-VL 30B FP8 + Whisper turbo, 48GB VRAM search, 100GB disk, $0.50/h cap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
