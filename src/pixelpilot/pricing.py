"""Pure offer-cost helpers; estimates are not invoices or transfer meters."""
from __future__ import annotations

import math
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pixelpilot.domain import GpuOffer

# Explicit decimal display convention: 1 TB = 1,000 GB.
GB_PER_TB = 1000.0


def nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def bandwidth_rate(raw: dict[str, Any], direction: str) -> float | None:
    """Vast's inet_*_cost is USD/GB, not USD/TB; invalid is not free."""
    if direction not in {"down", "up"}:
        raise ValueError("direction must be down or up")
    native = f"inet_{direction}_cost"
    if native in raw:
        return nonnegative_number(raw[native])
    per_tb = nonnegative_number(raw.get(f"internet_{direction}_cost_per_tb"))
    return None if per_tb is None else per_tb / GB_PER_TB


def download_estimate(offer: GpuOffer, download_gb: float) -> float | None:
    size = nonnegative_number(download_gb)
    if size is None:
        raise ValueError("download_gb must be finite and nonnegative")
    rate = offer.download_usd_per_gb
    return None if rate is None else nonnegative_number(rate * size)


def session_estimate(offer: GpuOffer, download_gb: float, billed_hours: float) -> float | None:
    hours = nonnegative_number(billed_hours)
    if hours is None:
        raise ValueError("billed_hours must be finite and nonnegative")
    transfer = download_estimate(offer, download_gb)
    # dph_total already includes the requested disk: do not add storage twice.
    return None if transfer is None else nonnegative_number(offer.price_per_hour * hours + transfer)


def offer_cost_rank(
    offer: GpuOffer, *, download_gb: float, billed_hours: float, preferred_vram_gb: int
) -> tuple[float, ...]:
    estimate = session_estimate(offer, download_gb, billed_hours)
    fallback = float(offer.gpu_ram_gb < preferred_vram_gb)
    if estimate is None:
        # Unknown transfer prices follow known quotes, never masquerade as $0.
        return (1.0, fallback, offer.price_per_hour, -(offer.dlperf or 0.0))
    return (0.0, estimate, fallback, offer.price_per_hour,
            -(offer.inet_down_mbps or 0.0), -(offer.dlperf or 0.0))


def download_rate_allowed(offer: GpuOffer, max_usd_per_tb: float | None) -> bool:
    if max_usd_per_tb is None:
        return True
    cap = nonnegative_number(max_usd_per_tb)
    if cap is None:
        raise ValueError("download price ceiling must be finite and nonnegative")
    rate = offer.download_usd_per_gb
    return rate is not None and rate <= cap / GB_PER_TB


def offer_cost_lines(offer: GpuOffer, *, download_gb: float, billed_hours: float) -> list[str]:
    def rate_line(label: str, rate: float | None) -> str:
        if rate is None:
            return f"{label}: <b>غير معروف — ليس مجانيًا</b>"
        return f"{label}: <b>${rate * GB_PER_TB:.8g}/TB</b> (${rate:.8g}/GB)"

    lines = [
        rate_line("⬇️ Download إلى السيرفر", offer.download_usd_per_gb),
        rate_line("⬆️ Upload من السيرفر", offer.upload_usd_per_gb),
    ]
    transfer = download_estimate(offer, download_gb)
    estimate = session_estimate(offer, download_gb, billed_hours)
    if transfer is None or estimate is None:
        lines.append("⚠️ لا يمكن تقدير تكلفة التجهيز دون سعر Download صالح؛ راجع Vast قبل التأكيد.")
    else:
        lines.extend([
            f"📦 تنزيل تجهيزي مفترض {download_gb:g} GB: <b>${transfer:.4f}</b>",
            f"🧮 {billed_hours:g} ساعة تشغيل + هذا التنزيل: <b>≈ ${estimate:.4f}</b>",
        ])
        if transfer > offer.price_per_hour * billed_hours:
            lines.append("⚠️ تكلفة التنزيل المفترضة أكبر من تكلفة مدة التشغيل المقارنة.")
    lines.append("التقدير ليس فاتورة: الحجم افتراضي، والساعة تشمل القرص؛ الرفع والتنزيلات اللاحقة غير مشمولة. 1 TB = 1000 GB.")
    lines.append("نماذج Qwen Enhance تُنزّل عند طلب التحسين فقط، وقد تضيف رسوم تنزيل.")
    return lines
