from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pixelpilot.domain import GpuOffer


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ إعدادات المساعد", callback_data="assistant:settings")],
            [
                InlineKeyboardButton(text="💬 طريقة الاستخدام", callback_data="chat:help"),
                InlineKeyboardButton(text="🧹 محادثة جديدة", callback_data="chat:new"),
            ],
            [InlineKeyboardButton(text="🔎 البحث عن سيرفر", callback_data="servers:search")],
            [
                InlineKeyboardButton(text="📊 حالة السيرفر", callback_data="servers:status"),
                InlineKeyboardButton(text="🧪 فحص الجاهزية", callback_data="servers:preflight"),
            ],
            [
                InlineKeyboardButton(text="▶️ تشغيل", callback_data="servers:start"),
                InlineKeyboardButton(text="⏹ إيقاف", callback_data="servers:stop"),
            ],
            [InlineKeyboardButton(text="🗑 حذف السيرفر", callback_data="servers:destroy_confirm")],
        ]
    )


def offers_keyboard(offers: list[GpuOffer]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔍 {offer.display_name}",
                callback_data=f"servers:offer:{offer.offer_id}",
            )
        ]
        for offer in offers
    ]
    rows.append([InlineKeyboardButton(text="🔄 تحديث العروض", callback_data="servers:search")])
    rows.append([InlineKeyboardButton(text="⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def offer_confirm_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 استئجار وتجهيز",
                    callback_data=f"servers:rent:{offer_id}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ رجوع للعروض", callback_data="servers:search")],
        ]
    )


def destroy_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 نعم، احذف نهائيًا", callback_data="servers:destroy")],
            [InlineKeyboardButton(text="إلغاء", callback_data="home")],
        ]
    )
