from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu

router = Router(name="home")


WELCOME = (
    "🤖 <b>PixelPilot</b>\n\n"
    "مساعد شخصي يعمل على GPU مؤقت في Vast.ai باستخدام Qwen3-Omni.\n"
    "بعد تجهيز السيرفر، أرسل للبوت مباشرة نصًا أو صورة أو تسجيلًا صوتيًا.\n\n"
    "لا توجد أوضاع لغة ولا برومبت داخلي؛ PixelPilot يمرر محادثتك للموديل كما هي."
)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(WELCOME, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "home")
async def home(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(WELCOME, reply_markup=main_menu())
