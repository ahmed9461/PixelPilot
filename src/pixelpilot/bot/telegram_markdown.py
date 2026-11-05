"""Render untrusted model Markdown as safe Telegram message entities.

Telegram does not interpret CommonMark directly. We deliberately avoid passing
model-generated HTML or MarkdownV2 to Telegram, and calculate UTF-16 offsets for
emoji/non-BMP characters as required by the Telegram Bot API.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from urllib.parse import urlsplit

from aiogram.types import MessageEntity
from markdown_it import MarkdownIt


MAX_TELEGRAM_UTF16 = 3900  # Telegram permits 4096; leave a buffer.
MAX_ENTITIES_PER_CHUNK = 90


@dataclass(frozen=True)
class TelegramChunk:
    text: str
    entities: tuple[MessageEntity, ...]


class _Builder:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.offset = 0
        self.trailing_newlines = 0
        self.spans: list[tuple[str, int, int, dict[str, str]]] = []

    def add(self, text: str) -> None:
        if not text:
            return
        self.parts.append(text)
        self.offset += len(text.encode("utf-16-le")) // 2
        trailing = len(text) - len(text.rstrip("\n"))
        self.trailing_newlines = (
            self.trailing_newlines + trailing if trailing == len(text) else trailing
        )

    def newline(self, count: int) -> None:
        if self.offset and self.trailing_newlines < count:
            self.add("\n" * (count - self.trailing_newlines))

    def span(self, kind: str, start: int, *, attrs: dict[str, str] | None = None) -> None:
        if self.offset > start:
            self.spans.append((kind, start, self.offset, attrs or {}))


def _safe_link(href: str) -> str | None:
    try:
        parts = urlsplit(href)
    except ValueError:
        return None
    return href if parts.scheme.lower() in {"http", "https"} and parts.netloc else None


def _inline(builder: _Builder, children: list, *, heading: bool = False) -> None:
    opened: list[tuple[str, int, dict[str, str]]] = []
    kinds = {
        "strong": "bold", "em": "italic", "s": "strikethrough",
        "link": "text_link",
    }
    for child in children:
        kind = child.type
        if kind in {"text", "text_special", "html_inline"}:
            builder.add(child.content)
        elif kind in {"softbreak", "hardbreak"}:
            builder.add("\n")
        elif kind == "code_inline":
            start = builder.offset
            builder.add(child.content)
            if not heading:
                builder.span("code", start)
        elif kind == "image":
            builder.add(child.content or "صورة")
        elif kind.endswith("_open") and kind.removesuffix("_open") in kinds:
            base = kind.removesuffix("_open")
            extra: dict[str, str] = {}
            if base == "link":
                href = _safe_link(child.attrGet("href") or "")
                if href:
                    extra["url"] = href
            opened.append((base, builder.offset, extra))
        elif kind.endswith("_close") and kind.removesuffix("_close") in kinds:
            base = kind.removesuffix("_close")
            if opened and opened[-1][0] == base:
                name, start, extra = opened.pop()
                if not heading and (name != "link" or extra.get("url")):
                    builder.span(kinds[name], start, attrs=extra)
        else:
            # Unknown markup should never execute, nor delete textual content.
            if child.content:
                builder.add(child.content)


def _build(markdown: str) -> tuple[str, list[tuple[str, int, int, dict[str, str]]]]:
    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    parser.enable("table")
    parser.enable("strikethrough")
    builder = _Builder()
    list_stack: list[dict[str, int | str]] = []
    heading_start: int | None = None
    cell_start: int | None = None
    cell_kind: str | None = None
    table_cell = 0

    for token in parser.parse(markdown):
        kind = token.type
        if kind == "heading_open":
            builder.newline(2)
            heading_start = builder.offset
        elif kind == "heading_close":
            if heading_start is not None:
                builder.span("bold", heading_start)
            heading_start = None
            builder.newline(2)
        elif kind == "inline":
            _inline(builder, token.children or [], heading=heading_start is not None)
        elif kind == "paragraph_close":
            if not list_stack and heading_start is None:
                builder.newline(2)
        elif kind in {"bullet_list_open", "ordered_list_open"}:
            start = token.attrGet("start")
            list_stack.append({
                "type": "ordered" if kind == "ordered_list_open" else "bullet",
                "counter": int(start) if start and str(start).isdigit() else 1,
            })
        elif kind in {"bullet_list_close", "ordered_list_close"}:
            if list_stack:
                list_stack.pop()
            builder.newline(2 if not list_stack else 1)
        elif kind == "list_item_open":
            builder.newline(1)
            current = list_stack[-1] if list_stack else {"type": "bullet", "counter": 1}
            if current["type"] == "ordered":
                marker = f"{current['counter']}. "
                current["counter"] = int(current["counter"]) + 1
            else:
                marker = "• "
            builder.add("  " * max(0, len(list_stack) - 1) + marker)
        elif kind == "list_item_close":
            builder.newline(1)
        elif kind in {"fence", "code_block"}:
            builder.newline(1)
            start = builder.offset
            builder.add(token.content.rstrip("\n"))
            builder.span("pre", start)
            builder.newline(2)
        elif kind == "blockquote_open":
            builder.newline(1)
            builder.add("❝ ")
        elif kind == "blockquote_close":
            builder.newline(2)
        elif kind == "hr":
            builder.newline(1)
            builder.add("──────────")
            builder.newline(2)
        elif kind == "tr_open":
            table_cell = 0
            builder.newline(1)
        elif kind in {"th_open", "td_open"}:
            if table_cell:
                builder.add("  |  ")
            table_cell += 1
            cell_start = builder.offset
            cell_kind = kind
        elif kind in {"th_close", "td_close"}:
            if cell_kind == "th_open" and cell_start is not None:
                builder.span("bold", cell_start)
            cell_start = None
            cell_kind = None
        elif kind == "tr_close":
            builder.newline(1)
        elif kind == "table_close":
            builder.newline(2)
        elif kind in {"html_block", "text"}:
            builder.add(token.content)

    output = "".join(builder.parts).rstrip("\n")
    return output, builder.spans


def format_model_reply(markdown: str) -> list[TelegramChunk]:
    """Format Markdown with entity-aware splitting at Telegram's UTF-16 limit."""
    text, spans = _build(markdown)
    if not text:
        return [TelegramChunk("…", ())]

    # Prefixes map Python string boundaries to Telegram UTF-16 code units.
    units = [0]
    for character in text:
        units.append(units[-1] + (2 if ord(character) > 0xFFFF else 1))

    chunks: list[TelegramChunk] = []
    start = 0
    while start < len(text):
        end = bisect_right(units, units[start] + MAX_TELEGRAM_UTF16) - 1
        if end < len(text):
            # Prefer whole paragraphs, but still make progress for long code blocks.
            newline = text.rfind("\n", start, end)
            if newline >= start + (end - start) // 2:
                end = newline + 1
        if end <= start:
            raise ValueError("Telegram message splitting made no progress")

        low, high = units[start], units[end]
        entities: list[MessageEntity] = []
        for kind, first, last, options in spans:
            left, right = max(low, first), min(high, last)
            if right > left and len(entities) < MAX_ENTITIES_PER_CHUNK:
                entities.append(MessageEntity(
                    type=kind, offset=left - low, length=right - left,
                    **options,
                ))
        entities.sort(key=lambda entity: (entity.offset, -entity.length))
        chunks.append(TelegramChunk(text[start:end], tuple(entities)))
        start = end

    return chunks
