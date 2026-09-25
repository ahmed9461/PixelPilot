from pixelpilot.bot.keyboards import offer_confirm_keyboard, offers_keyboard
from pixelpilot.domain import GpuOffer


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_normal_offer_keyboard_can_switch_to_48gb_only():
    markup = offers_keyboard(
        [GpuOffer(1, "RTX A6000", 48, 0.4, 0.99, 40)],
        preferred_only=False,
    )
    callbacks = _callbacks(markup)
    assert "servers:offer:1:a" in callbacks
    assert "servers:search" in callbacks
    assert "servers:search48" in callbacks


def test_preferred_offer_keyboard_refreshes_preferred_mode_and_can_show_all():
    markup = offers_keyboard(
        [GpuOffer(1, "RTX A6000", 48, 0.4, 0.99, 40)],
        preferred_only=True,
    )
    callbacks = _callbacks(markup)
    assert "servers:offer:1:p" in callbacks
    assert "servers:search48" in callbacks
    assert "servers:search" in callbacks


def test_offer_details_back_button_preserves_search_mode():
    normal = _callbacks(offer_confirm_keyboard(1, preferred_only=False))
    preferred = _callbacks(offer_confirm_keyboard(1, preferred_only=True))
    assert normal[-1] == "servers:search"
    assert preferred[-1] == "servers:search48"
    assert "servers:rent:1:p" in preferred
