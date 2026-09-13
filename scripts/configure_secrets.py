from __future__ import annotations

import getpass
from pathlib import Path

from pixelpilot.setup_env import write_private_env


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def _secret(label: str) -> str:
    return getpass.getpass(f"{label}: ").strip()


def main() -> int:
    print("PixelPilot secure first-run configuration")
    print("Secrets are written only to .env (gitignored) and are not echoed.\n")

    if TARGET.exists():
        answer = input(".env already exists. Replace it? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled; existing .env was left unchanged.")
            return 0

    values = {
        "TELEGRAM_BOT_TOKEN": _secret("Telegram Bot Token"),
        "OWNER_TELEGRAM_ID": input("Telegram numeric User ID: ").strip(),
        "VAST_API_KEY": _secret("Vast.ai API Key"),
        "HF_TOKEN": _secret("Hugging Face Read Token"),
    }

    print("\nChoose how temporary Vast instances obtain PixelPilot:")
    print("1) Git repository URL (recommended for now)")
    print("2) Vast template hash")
    mode = input("Choice [1/2]: ").strip() or "1"
    if mode == "2":
        values["VAST_TEMPLATE_HASH"] = input("Vast template hash: ").strip()
        values["PIXELPILOT_REPO_URL"] = ""
    else:
        values["PIXELPILOT_REPO_URL"] = input("PixelPilot Git repository URL: ").strip()
        values["PIXELPILOT_REPO_REF"] = input("Git ref [main]: ").strip() or "main"
        values["VAST_TEMPLATE_HASH"] = ""

    try:
        write_private_env(TEMPLATE, TARGET, values)
    except ValueError as exc:
        print(f"Configuration failed: {exc}")
        return 1

    print("\nSaved private configuration to .env")
    print("Next: python scripts/preflight.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
