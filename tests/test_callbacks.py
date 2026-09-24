import asyncio

import pytest
from aiogram.exceptions import TelegramBadRequest

from pixelpilot.bot.callbacks import safe_callback_answer, safe_edit_text


class _Callback:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = 0

    async def answer(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error


def test_safe_callback_answer_success():
    callback = _Callback()
    result = asyncio.run(safe_callback_answer(callback, "ok"))
    assert result is True
    assert callback.calls == 1


def test_safe_callback_answer_ignores_expired_query():
    error = TelegramBadRequest(method="answerCallbackQuery", message="query is too old and response timeout expired or query ID is invalid")
    callback = _Callback(error)
    result = asyncio.run(safe_callback_answer(callback, "ok"))
    assert result is False


def test_safe_callback_answer_reraises_other_bad_request():
    error = TelegramBadRequest(method="answerCallbackQuery", message="some unrelated bad request")
    callback = _Callback(error)
    with pytest.raises(TelegramBadRequest):
        asyncio.run(safe_callback_answer(callback, "ok"))



class _Message:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = 0

    async def edit_text(self, text, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error


def test_safe_edit_text_ignores_not_modified():
    error = TelegramBadRequest(
        method="editMessageText",
        message="Bad Request: message is not modified",
    )
    message = _Message(error)
    result = asyncio.run(safe_edit_text(message, "same"))
    assert result is False
    assert message.calls == 1
