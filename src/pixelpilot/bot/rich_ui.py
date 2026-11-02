from __future__ import annotations

from typing import Mapping

from aiogram.types import InputRichMessage


def home_card() -> InputRichMessage:
    return InputRichMessage(
        is_rtl=True,
        html=(
            "<h2>🧠 PixelPilot</h2>"
            "<p>مساعد شخصي للدردشة وفهم الصور وإنشائها وتعديلها.</p>"
            "<p>أرسل رسالة للدردشة، صورة لتحليلها، أو اختر إنشاء/تعديل الصور من الأزرار.</p>"
            "<details><summary>ما الذي يدعمه؟</summary>"
            "<ul>"
            "<li>محادثة عربية مستمرة مع سجل نصي</li><li>فهم الصور وقراءة النصوص فيها</li><li>توليد صورة من وصف نصي</li>"
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
            f"<p>وضع البرومت: <b>{values.get('prompt_mode', '')}</b></p>"
            f"<p>الجودة: <b>{values.get('quality', '')}</b></p>"
            f"<p>النسبة: <b>{values.get('aspect_ratio', '')}</b></p>"
            f"<p>الخطوات: <b>{values.get('steps', '')}</b></p>"
        ),
    )
