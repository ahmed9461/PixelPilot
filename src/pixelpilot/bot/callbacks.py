from __future__ import annotations

import logging
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)

_STALE_CALLBACK_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
)

_NOT_MODIFIED_MARKERS = (
    "message is not modified",
    "message not modified",
)


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> bool:
    """Acknowledge a Telegram callback without letting stale queries break the action."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
        return True
    except TelegramBadRequest as exc:
        message = str(exc).lower()
        if any(marker in message for marker in _STALE_CALLBACK_MARKERS):
            logger.info("Ignoring expired Telegram callback query: %s", exc)
            return False
        raise


async def safe_edit_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Edit a message and quietly ignore Telegram's harmless no-change response.

    Inline settings buttons can legitimately resolve to the screen already on
    display (for example tapping the selected option twice). Telegram returns
    Bad Request in that case; treating it as a successful no-op avoids the
    apparent button glitch and noisy handler failures.
    """
    kwargs: dict[str, Any] = {"reply_markup": reply_markup}
    if parse_mode is not None:
        kwargs["parse_mode"] = parse_mode
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as exc:
        lowered = str(exc).lower()
        if any(marker in lowered for marker in _NOT_MODIFIED_MARKERS):
            logger.debug("Ignoring unchanged Telegram message edit: %s", exc)
            return False
        raise


async def safe_edit_reply_markup(
    message: Message,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    try:
        await message.edit_reply_markup(reply_markup=reply_markup)
        return True
    except TelegramBadRequest as exc:
        lowered = str(exc).lower()
        if any(marker in lowered for marker in _NOT_MODIFIED_MARKERS):
            logger.debug("Ignoring unchanged Telegram markup edit: %s", exc)
            return False
        raise
