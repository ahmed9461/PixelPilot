from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.keyboards import main_menu

router = Router(name="home")


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "✈️ <b>PixelPilot</b>\n\n"
        "إدارة GPU مؤقت + توليد صور من تلجرام.\n"
        "اختر ما تريد:",
        reply_markup=main_menu(),
    )


@router.callback_query(lambda q: q.data == "home")
async def home(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("✈️ <b>PixelPilot</b>\n\nاختر ما تريد:", reply_markup=main_menu())
