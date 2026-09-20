from __future__ import annotations

from html import escape
from typing import Mapping

from aiogram.types import InputRichMessage


def home_card() -> InputRichMessage:
    return InputRichMessage(
        is_rtl=True,
        html=(
            "<h2>🤖 PixelPilot</h2>"
            "<p>مساعدك الشخصي متعدد الوسائط.</p>"
            "<p>بعد تجهيز السيرفر، أرسل رسالتك مباشرة وابدأ المحادثة.</p>"
            "<details><summary>ما الذي أستطيع إرساله؟</summary>"
            "<ul>"
            "<li>نص</li>"
            "<li>صورة</li>"
            "<li>صوت أو تسجيل صوتي</li>"
            "<li>فيديو</li>"
            "</ul>"
            "</details>"
            "<footer>اختر من الأزرار بالأسفل للتحكم بالمساعد والسيرفر.</footer>"
        ),
    )


def settings_card(values: Mapping[str, str | int]) -> InputRichMessage:
    rows = [
        ("🎭 الروح", str(values["persona"])),
        ("⚡ السمة", str(values["tone"])),
        ("🧠 الاستدلال", str(values["reasoning"])),
        ("🧾 التنسيق", str(values["format"])),
        ("🌐 اللغة", str(values["language"])),
        ("🎨 الإبداع", f"{values['creativity']}%"),
        ("🧪 التنوع", f"{values['diversity']}%"),
        ("📏 طول الرد", f"{values['length']}%"),
        ("🔁 منع التكرار", f"{values['repetition']}%"),
        ("🧩 البرومت المخصص", str(values["custom"])),
    ]
    body = "".join(
        f"<tr><td>{escape(name)}</td><td><b>{escape(value)}</b></td></tr>"
        for name, value in rows
    )
    return InputRichMessage(
        is_rtl=True,
        html=(
            "<h2>⚙️ إعدادات المساعد</h2>"
            "<p>غيّر الشخصية وطريقة الرد والإعدادات المتقدمة مباشرة من هنا.</p>"
            f"<table bordered striped compact>{body}</table>"
            "<footer>أي تغيير تحفظه يطبق على الرسالة التالية.</footer>"
        ),
    )



def response_card(markdown: str) -> InputRichMessage:
    """Wrap a completed model response in Telegram's native rich renderer."""
    arabic = sum(1 for ch in markdown if "\u0600" <= ch <= "\u06ff")
    latin = sum(1 for ch in markdown if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    return InputRichMessage(
        markdown=markdown,
        is_rtl=arabic > latin,
    )
