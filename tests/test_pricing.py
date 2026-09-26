from dataclasses import replace
import math

import pytest

from pixelpilot.domain import GpuOffer
from pixelpilot.pricing import (
    bandwidth_rate, download_estimate, download_rate_allowed,
    nonnegative_number, offer_cost_lines, offer_cost_rank, session_estimate,
)


def offer(**kwargs):
    data = dict(offer_id=1, gpu_name="RTX A6000", gpu_ram_gb=48,
                price_per_hour=0.4, reliability=0.99, dlperf=40)
    data.update(kwargs)
    return GpuOffer(**data)


@pytest.mark.parametrize("value", [None, "", "invalid", -0.01, True, False,
                                   float("nan"), float("inf"), -float("inf")])
def test_invalid_rate_is_unknown_not_free(value):
    assert nonnegative_number(value) is None
    assert bandwidth_rate({"inet_down_cost": value}, "down") is None


def test_native_rate_units_precision_zero_and_alias():
    assert bandwidth_rate({"inet_down_cost": "0.026051779935275"}, "down") == 0.026051779935275
    assert bandwidth_rate({"inet_down_cost": 0}, "down") == 0
    assert bandwidth_rate({"internet_down_cost_per_tb": 5}, "down") == 0.005
    assert bandwidth_rate({"internet_up_cost_per_tb": 3}, "up") == 0.003
    assert bandwidth_rate({"inet_down_cost": 0.026, "internet_down_cost_per_tb": 999}, "down") == 0.026
    assert bandwidth_rate({"inet_down_cost": None, "internet_down_cost_per_tb": 0}, "down") is None
    with pytest.raises(ValueError):
        bandwidth_rate({}, "sideways")


def test_raw_quotes_are_persisted_and_legacy_snapshots_remain_unknown():
    live = offer(machine_id=116779, raw={"inet_down_cost": 0.026, "inet_up_cost": 0})
    saved = live.public_dict()
    assert "raw" not in saved
    assert saved["machine_id"] == 116779
    assert saved["download_usd_per_gb"] == 0.026
    restored = GpuOffer(**saved)
    assert restored.download_usd_per_gb == 0.026
    assert restored.upload_usd_per_gb == 0
    assert offer().download_usd_per_gb is None
    assert replace(live, download_usd_per_gb=0.005).download_usd_per_gb == 0.005
    assert "↓ $26/TB" in live.display_name


def test_download_and_running_period_are_separate_no_double_storage():
    quoted = offer(price_per_hour=0.45556, download_usd_per_gb=0.026)
    assert download_estimate(quoted, 70) == pytest.approx(1.82)
    assert session_estimate(quoted, 70, 1) == pytest.approx(2.27556)
    assert session_estimate(quoted, 70, 2) == pytest.approx(2.73112)
    assert download_estimate(offer(), 70) is None
    assert session_estimate(offer(), 70, 1) is None
    assert session_estimate(offer(download_usd_per_gb=0), 70, 1) == 0.4
    with pytest.raises(ValueError):
        download_estimate(quoted, -1)
    with pytest.raises(ValueError):
        session_estimate(quoted, 70, math.inf)


def test_rank_uses_cold_cost_not_only_hourly_or_vram():
    expensive_transfer = offer(offer_id=1, price_per_hour=0.2, download_usd_per_gb=0.03)
    free_transfer = offer(offer_id=2, gpu_ram_gb=24, price_per_hour=0.49, download_usd_per_gb=0)
    unknown = offer(offer_id=3, price_per_hour=0.1)
    rows = sorted([unknown, expensive_transfer, free_transfer], key=lambda row:
                  offer_cost_rank(row, download_gb=70, billed_hours=1, preferred_vram_gb=48))
    assert [row.offer_id for row in rows] == [2, 1, 3]


def test_optional_ceiling_preserves_free_and_rejects_unknown_when_enabled():
    assert download_rate_allowed(offer(), None)
    assert not download_rate_allowed(offer(), 5)
    assert download_rate_allowed(offer(download_usd_per_gb=0.005), 5)
    assert not download_rate_allowed(offer(download_usd_per_gb=0.00500001), 5)
    assert download_rate_allowed(offer(download_usd_per_gb=0), 0)
    assert not download_rate_allowed(offer(download_usd_per_gb=0.0000001), 0)
    with pytest.raises(ValueError):
        download_rate_allowed(offer(), -1)


def test_cost_ui_warns_about_unknown_expensive_transfer_and_estimation():
    expensive = "\n".join(offer_cost_lines(offer(download_usd_per_gb=0.026), download_gb=70, billed_hours=1))
    assert "$26/TB" in expensive
    assert "$0.026/GB" in expensive
    assert "$1.8200" in expensive
    assert "أكبر من تكلفة" in expensive
    assert "ليس فاتورة" in expensive
    unknown = "\n".join(offer_cost_lines(offer(), download_gb=70, billed_hours=1))
    assert "غير معروف — ليس مجانيًا" in unknown
    assert "لا يمكن تقدير" in unknown
    assert "1 TB = 1000 GB" in unknown
