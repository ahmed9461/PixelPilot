from pixelpilot.bot.routers.servers import _refresh_note
from pixelpilot.domain import GpuOffer


def _offer(offer_id: int, price: float) -> GpuOffer:
    return GpuOffer(
        offer_id=offer_id,
        gpu_name="A6000",
        gpu_ram_gb=48,
        price_per_hour=price,
        reliability=0.99,
        dlperf=40,
        inet_down_mbps=1000,
    )


def test_refresh_reports_unchanged_market():
    previous = [_offer(1, 0.40).public_dict()]
    current = [_offer(1, 0.40)]
    assert "لا توجد تغييرات" in _refresh_note(previous, current)


def test_refresh_reports_new_and_removed_offers():
    previous = [_offer(1, 0.40).public_dict()]
    current = [_offer(2, 0.42)]
    note = _refresh_note(previous, current)
    assert "1 عرض جديد" in note
    assert "1 عرض اختفى" in note


def test_refresh_detects_price_change_for_same_offer():
    previous = [_offer(1, 0.40).public_dict()]
    current = [_offer(1, 0.45)]
    assert "تغيّرت الأسعار" in _refresh_note(previous, current)
