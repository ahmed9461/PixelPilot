"""Shared, bounded controller/worker contracts. No model or web imports."""
from __future__ import annotations

import io
import re
from typing import Any

MAX_PROMPT_CHARS = 12_000
MAX_HISTORY_CHARS = 16_000
MAX_TURN_CHARS = 4_000
MAX_HISTORY_MESSAGES = 20
MAX_CHAT_INPUT_TOKENS = 8_192
MAX_TOTAL_IMAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
GATEWAY_API_VERSION = 2


def trim_history(value: Any, *, max_turns: int = 8) -> list[dict[str, str]]:
    """Keep the newest complete user/assistant pairs within both limits.

    Old databases and malformed rows are tolerated. A prior incomplete user
    turn is never paired with an unrelated future answer. No images or extra
    keys can be serialized back into conversation memory.
    """
    if not isinstance(value, list):
        return []
    pairs: list[list[dict[str, str]]] = []
    pending: dict[str, str] | None = None
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("content"), str):
            pending = None
            continue
        content = row["content"][:MAX_TURN_CHARS]
        role = row.get("role")
        if not content.strip() or role not in {"user", "assistant"}:
            pending = None
            continue
        turn = {"role": role, "content": content}
        if role == "user":
            pending = turn
        elif pending is not None:
            pairs.append([pending, turn])
            pending = None
    selected: list[list[dict[str, str]]] = []
    chars = 0
    for pair in reversed(pairs[-max(1, min(int(max_turns), MAX_HISTORY_MESSAGES // 2)):]):
        size = sum(len(turn["content"]) for turn in pair)
        if chars + size > MAX_HISTORY_CHARS:
            break
        selected.append(pair)
        chars += size
    return [turn for pair in reversed(selected) for turn in pair]


def visible_reply(text: str) -> str:
    """Remove closed AND truncated thinking spans before displaying a reply."""
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL | re.IGNORECASE)
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    text = re.split(r"<think>", text, maxsplit=1, flags=re.IGNORECASE)[0]
    return text.strip()


def telegram_chunks(text: str, *, limit: int = 3500) -> list[str]:
    """Split by UTF-16 units so emoji-heavy replies also fit Telegram."""
    if limit < 2:
        raise ValueError("chunk limit must be at least two UTF-16 units")
    chunks: list[str] = []
    part: list[str] = []
    size = 0
    for char in text:
        units = 2 if ord(char) > 0xFFFF else 1
        if size + units > limit:
            chunks.append("".join(part))
            part, size = [], 0
        part.append(char)
        size += units
    if part:
        chunks.append("".join(part))
    return chunks


class BoundedBuffer(io.BytesIO):
    """Reject oversized downloads while bytes arrive, not after allocation."""
    def __init__(self, max_bytes: int):
        super().__init__()
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = max_bytes

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self.max_bytes:
            raise ValueError("Image exceeds the allowed byte limit")
        return super().write(data)
