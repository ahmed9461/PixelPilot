from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu

router = Router(name="home")


WELCOME = (
    "🤖 <b>PixelPilot</b>\n\n"
    "مساعدك الشخصي.\n"
    "بعد تجهيز السيرفر، أرسل نصًا أو صورة أو تسجيلًا صوتيًا وابدأ المحادثة مباشرة."
)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(WELCOME, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "home")
async def home(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(WELCOME, reply_markup=main_menu())
