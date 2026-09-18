from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.bot.rich_ui import home_card

router = Router(name="home")


WELCOME = (
    "🤖 <b>PixelPilot</b>\n\n"
    "مساعدك الشخصي.\n"
    "بعد تجهيز السيرفر، أرسل نصًا أو صورة أو صوتًا أو فيديو وابدأ المحادثة مباشرة."
)


@router.message(CommandStart())
async def start(message: Message) -> None:
    try:
        await message.bot.send_rich_message(
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            rich_message=home_card(),
            reply_markup=main_menu(),
        )
    except Exception:
        await message.answer(WELCOME, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "home")
async def home(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    try:
        await callback.message.edit_text(
            rich_message=home_card(),
            reply_markup=main_menu(),
        )
    except Exception:
        await callback.message.edit_text(WELCOME, reply_markup=main_menu())
