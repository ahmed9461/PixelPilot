from pixelpilot.bot.rich_ui import home_card, response_card, settings_card


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
            "creativity": 70,
            "diversity": 80,
            "length": 100,
            "repetition": 0,
        }
    )
    assert card.is_rtl is True
    assert "<table bordered striped compact>" in (card.html or "")
    assert "70%" in (card.html or "")



def test_response_card_detects_rtl_and_preserves_markdown():
    arabic = response_card("## عنوان\n\nمرحبا بك")
    assert arabic.markdown == "## عنوان\n\nمرحبا بك"
    assert arabic.is_rtl is True

    english = response_card("## Hello\n\nHow are you?")
    assert english.is_rtl is False
