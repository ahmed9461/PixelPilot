from __future__ import annotations

from typing import Mapping

from aiogram.types import InputRichMessage


def home_card() -> InputRichMessage:
    return InputRichMessage(
        is_rtl=True,
        html=(
            "<h2>🎨 PixelPilot</h2>"
            "<p>استوديو شخصي لإنشاء الصور وتعديلها.</p>"
            "<p>أرسل وصفك كنص، أو أرسل صورة مع تعليمات التعديل.</p>"
            "<details><summary>ما الذي يدعمه؟</summary>"
            "<ul>"
            "<li>توليد صورة من وصف نصي</li>"
            "<li>تعديل صورة واحدة</li>"
            "<li>استخدام ألبوم صور كمراجع متعددة</li>"
            "<li>اختيار النسبة والجودة وخطوات التوليد</li>"
            "</ul>"
            "</details>"
            "<footer>لا توجد شخصية أو نبرة أو برومت مخفي يغيّر طلبك.</footer>"
        ),
    )


def settings_card(values: Mapping[str, str | int]) -> InputRichMessage:
    return InputRichMessage(
        is_rtl=True,
        html=(
            "<h2>⚙️ إعدادات الصور</h2>"
            f"<p>الجودة: <b>{values.get('quality', '')}</b></p>"
            f"<p>النسبة: <b>{values.get('aspect_ratio', '')}</b></p>"
            f"<p>الخطوات: <b>{values.get('steps', '')}</b></p>"
        ),
    )
