from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)

_STALE_CALLBACK_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
)


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> bool:
    """Answer a callback query without aborting the real action if Telegram says it expired.

    Telegram callback answers have a short validity window. A queued/stale update can still
    reach the bot after that window, and answerCallbackQuery then returns Bad Request. The
    business action (search, rent, destroy, generation, etc.) should not crash solely because
    the acknowledgement bubble could not be displayed.

    Returns True when Telegram accepted the acknowledgement, False when it was stale.
    Other TelegramBadRequest errors are re-raised because they may indicate a real bug.
    """

    try:
        await callback.answer(text=text, show_alert=show_alert)
        return True
    except TelegramBadRequest as exc:
        message = str(exc).lower()
        if any(marker in message for marker in _STALE_CALLBACK_MARKERS):
            logger.info("Ignoring expired Telegram callback query: %s", exc)
            return False
        raise
