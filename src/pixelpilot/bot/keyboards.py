from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pixelpilot.domain import GpuOffer


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧠 الدردشة الذكية", callback_data="chat:mode:chat", style="primary"),
                InlineKeyboardButton(text="👁️ فهم الصور", callback_data="chat:mode:vision"),
            ],
            [
                InlineKeyboardButton(text="🎨 إنشاء صور", callback_data="chat:mode:generate"),
                InlineKeyboardButton(text="🖌️ تعديل صور", callback_data="chat:mode:edit"),
            ],
            [InlineKeyboardButton(text="⚙️ إعدادات الصور", callback_data="imagesettings:open", style="primary")],
            [InlineKeyboardButton(text="🎨 طريقة الاستخدام", callback_data="chat:help")],
            [InlineKeyboardButton(text="🔎 البحث عن سيرفر", callback_data="servers:search", style="primary")],
            [InlineKeyboardButton(text="🚀 سيرفرات 80GB+", callback_data="servers:search80"), InlineKeyboardButton(text="🔥 سيرفرات 48GB+", callback_data="servers:search48")],
            [
                InlineKeyboardButton(text="📊 حالة السيرفر", callback_data="servers:status"),
                InlineKeyboardButton(text="🧪 فحص الجاهزية", callback_data="servers:preflight"),
            ],
            [
                InlineKeyboardButton(text="▶️ تشغيل", callback_data="servers:start", style="success"),
                InlineKeyboardButton(text="⏹ إيقاف", callback_data="servers:stop", style="danger"),
            ],
            [InlineKeyboardButton(text="🗑 حذف السيرفر", callback_data="servers:destroy_confirm", style="danger")],
        ]
    )


def offers_keyboard(
    offers: list[GpuOffer],
    *,
    preferred_only: bool = False,
    premium_only: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔍 {offer.display_name} • #{offer.offer_id}",
                callback_data=f"servers:offer:{offer.offer_id}:{'h' if premium_only else ('p' if preferred_only else 'a')}",
                style="primary",
            )
        ]
        for offer in offers
    ]
    refresh_callback = "servers:search80" if premium_only else ("servers:search48" if preferred_only else "servers:search")
    rows.append([
        InlineKeyboardButton(
            text="🔄 تحديث العروض",
            callback_data=refresh_callback,
            style="primary",
        )
    ])
    if premium_only:
        rows.append([InlineKeyboardButton(text="🔥 عروض 48GB+", callback_data="servers:search48")])
        rows.append([InlineKeyboardButton(text="🌐 كل العروض", callback_data="servers:search")])
    elif preferred_only:
        rows.append([InlineKeyboardButton(text="🚀 عروض 80GB+", callback_data="servers:search80")])
        rows.append([
            InlineKeyboardButton(
                text="🌐 عرض كل العروض",
                callback_data="servers:search",
            )
        ])
    else:
        rows.append([InlineKeyboardButton(text="🚀 عروض 80GB+", callback_data="servers:search80")])
        rows.append([
            InlineKeyboardButton(
                text="🔥 48GB+ فقط",
                callback_data="servers:search48",
                style="success",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def offer_confirm_keyboard(
    offer_id: int,
    *,
    preferred_only: bool = False,
    premium_only: bool = False,
    quote: str | None = None,
) -> InlineKeyboardMarkup:
    back_callback = "servers:search80" if premium_only else ("servers:search48" if preferred_only else "servers:search")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 استئجار وتجهيز",
                    callback_data=f"servers:rent:{offer_id}:{'h' if premium_only else ('p' if preferred_only else 'a')}" + (f":{quote}" if quote else ""),
                    style="success",
                )
            ],
            [InlineKeyboardButton(text="⬅️ رجوع للعروض", callback_data=back_callback)],
        ]
    )


def destroy_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 نعم، احذف نهائيًا", callback_data="servers:destroy", style="danger")],
            [InlineKeyboardButton(text="إلغاء", callback_data="home")],
        ]
    )
