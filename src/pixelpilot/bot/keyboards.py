from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pixelpilot.domain import GpuOffer


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 البحث عن سيرفر", callback_data="servers:search")],
        [InlineKeyboardButton(text="🎨 إنشاء صورة", callback_data="generate:start")],
        [InlineKeyboardButton(text="📊 حالة السيرفر", callback_data="servers:status")],
        [InlineKeyboardButton(text="🧪 فحص الجاهزية", callback_data="servers:preflight")],
        [
            InlineKeyboardButton(text="▶️ تشغيل", callback_data="servers:start"),
            InlineKeyboardButton(text="⏹ إيقاف", callback_data="servers:stop"),
        ],
        [InlineKeyboardButton(text="🗑 حذف السيرفر", callback_data="servers:destroy_confirm")],
    ])


def offers_keyboard(offers: list[GpuOffer]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🔍 {offer.display_name}", callback_data=f"servers:offer:{offer.offer_id}")]
        for offer in offers
    ]
    rows.append([InlineKeyboardButton(text="🔄 تحديث العروض", callback_data="servers:search")])
    rows.append([InlineKeyboardButton(text="⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def offer_confirm_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 استئجار وتجهيز", callback_data=f"servers:rent:{offer_id}")],
        [InlineKeyboardButton(text="⬅️ رجوع للعروض", callback_data="servers:search")],
    ])


def destroy_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 نعم، احذف نهائيًا", callback_data="servers:destroy")],
        [InlineKeyboardButton(text="إلغاء", callback_data="home")],
    ])


def preset_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📷 طبيعي", callback_data="generate:preset:natural"),
            InlineKeyboardButton(text="👤 بورتريه", callback_data="generate:preset:portrait"),
        ],
        [
            InlineKeyboardButton(text="🧍 كامل الجسم", callback_data="generate:preset:full_body"),
            InlineKeyboardButton(text="👗 أزياء", callback_data="generate:preset:fashion"),
        ],
        [
            InlineKeyboardButton(text="🌿 خارجي", callback_data="generate:preset:outdoor"),
            InlineKeyboardButton(text="📦 منتج", callback_data="generate:preset:product"),
        ],
        [InlineKeyboardButton(text="إلغاء", callback_data="generate:cancel")],
    ])


def ratio_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1:1", callback_data="generate:ratio:1x1"),
            InlineKeyboardButton(text="4:5", callback_data="generate:ratio:4x5"),
            InlineKeyboardButton(text="3:2", callback_data="generate:ratio:3x2"),
        ],
        [
            InlineKeyboardButton(text="16:9", callback_data="generate:ratio:16x9"),
            InlineKeyboardButton(text="9:16", callback_data="generate:ratio:9x16"),
        ],
        [InlineKeyboardButton(text="إلغاء", callback_data="generate:cancel")],
    ])


def count_keyboard(max_batch: int = 4) -> InlineKeyboardMarkup:
    choices = [n for n in (1, 2, 4) if n <= max_batch]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{n} صورة" if n == 1 else f"{n} صور", callback_data=f"generate:count:{n}") for n in choices],
        [InlineKeyboardButton(text="إلغاء", callback_data="generate:cancel")],
    ])


def generation_image_keyboard(generation_id: int, image_index: int, *, show_rerun: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text="📄 إرسال الأصل",
        callback_data=f"generate:original:{generation_id}:{image_index}",
    )]]
    if show_rerun:
        rows.append([
            InlineKeyboardButton(text="♻️ نفس Seed", callback_data=f"generate:rerun_same:{generation_id}"),
            InlineKeyboardButton(text="🎲 Seed جديد", callback_data=f"generate:rerun_new:{generation_id}"),
        ])
        rows.append([InlineKeyboardButton(text="🎨 صورة جديدة", callback_data="generate:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
