from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


SECRET_KEYS = {"TELEGRAM_BOT_TOKEN", "VAST_API_KEY", "HF_TOKEN"}
REQUIRED_KEYS = {"TELEGRAM_BOT_TOKEN", "OWNER_TELEGRAM_ID", "VAST_API_KEY"}


def render_env(template_text: str, updates: Mapping[str, str]) -> str:
    """Return an .env body while preserving comments/order from .env.example."""
    output: list[str] = []
    seen: set[str] = set()
    for line in template_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    return "\n".join(output).rstrip() + "\n"


def validate_setup_values(values: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_KEYS:
        if not str(values.get(key, "")).strip():
            errors.append(f"{key} is required")
    owner = str(values.get("OWNER_TELEGRAM_ID", "")).strip()
    if owner and (not owner.isdigit() or int(owner) <= 0):
        errors.append("OWNER_TELEGRAM_ID must be a positive numeric Telegram user id")
    if not str(values.get("PIXELPILOT_REPO_URL", "")).strip() and not str(
        values.get("VAST_TEMPLATE_HASH", "")
    ).strip():
        errors.append("PIXELPILOT_REPO_URL or VAST_TEMPLATE_HASH is required before renting")
    return errors


def write_private_env(
    template_path: Path,
    target_path: Path,
    values: Mapping[str, str],
) -> None:
    errors = validate_setup_values(values)
    if errors:
        raise ValueError("; ".join(errors))
    body = render_env(template_path.read_text(encoding="utf-8"), values)
    target_path.write_text(body, encoding="utf-8")
    try:
        os.chmod(target_path, 0o600)
    except OSError:
        pass
