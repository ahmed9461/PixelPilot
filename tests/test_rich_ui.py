from pixelpilot.bot.rich_ui import home_card, settings_card


def test_home_rich_message_is_rtl_and_image_focused():
    card = home_card()
    assert card.is_rtl is True
    assert "<h2>🎨 PixelPilot</h2>" in (card.html or "")
    assert "توليد صورة" in (card.html or "")
    assert "صوت" not in (card.html or "")


def test_settings_rich_message_contains_image_controls():
    card = settings_card(
        {
            "prompt_mode": "تحسين Qwen",
            "quality": "قياسي",
            "aspect_ratio": "1:1",
            "steps": 40,
        }
    )
    html = card.html or ""
    assert card.is_rtl is True
    assert "إعدادات الصور" in html
    assert "تحسين Qwen" in html
    assert "1:1" in html
    assert "40" in html
    assert "الشخصية" not in html
