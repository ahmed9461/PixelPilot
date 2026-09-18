from pixelpilot.bot.rich_ui import home_card, settings_card


def test_home_rich_message_is_rtl_and_structured():
    card = home_card()
    assert card.is_rtl is True
    assert "<h2>🤖 PixelPilot</h2>" in (card.html or "")
    assert "<details>" in (card.html or "")


def test_settings_rich_message_uses_table():
    card = settings_card(
        {
            "persona": "⚪ محايد",
            "tone": "🙂 متوازن",
            "reasoning": "✨ تلقائي",
            "format": "✨ تلقائي",
            "language": "🌐 تلقائي",
            "creativity": 0,
            "diversity": 100,
            "length": 100,
        }
    )
    assert card.is_rtl is True
    assert "<table bordered striped compact>" in (card.html or "")
    assert "0%" in (card.html or "")
