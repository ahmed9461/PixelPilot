"""One fail-closed hardware/price policy for discovery and pre-rent checks."""
from __future__ import annotations

import math
from pixelpilot.config import Settings
from pixelpilot.domain import GpuOffer
from pixelpilot.pricing import download_rate_allowed


def _at_least(value: float | None, minimum: float) -> bool:
    return (value is not None and not isinstance(value, bool)
            and math.isfinite(value) and value >= minimum)


def violations(offer: GpuOffer, settings: Settings, *, minimum_vram: int | None = None) -> list[str]:
    errors: list[str] = []
    price = offer.price_per_hour
    if not math.isfinite(price) or not 0 < price <= min(0.60, settings.vast_max_price_usd_hour):
        errors.append("hourly_price")
    floor = max(settings.vast_min_gpu_ram_gb, minimum_vram or 0)
    if not _at_least(offer.gpu_ram_gb, floor):
        errors.append("vram")
    if settings.vast_verified_only and offer.verified is not True:
        errors.append("verification")
    if not _at_least(offer.reliability, settings.vast_min_reliability) or (offer.reliability or 0) > 1:
        errors.append("reliability")
    if not _at_least(offer.inet_down_mbps, settings.vast_min_inet_down_mbps):
        errors.append("download_speed")
    if not _at_least(offer.inet_up_mbps, settings.vast_min_inet_up_mbps):
        errors.append("upload_speed")
    if not _at_least(offer.disk_space_gb, settings.vast_disk_gb):
        errors.append("disk_space")
    if offer.num_gpus != 1:
        errors.append("gpu_count")
    if not _at_least(offer.direct_port_count, settings.vast_min_direct_ports):
        errors.append("direct_ports")
    offload = (offer.gpu_ram_gb < settings.image_full_gpu_min_vram_gb
               or settings.image_memory_mode == "offload")
    if offload and not _at_least(offer.cpu_ram_gb, settings.vast_min_cpu_ram_gb):
        errors.append("offload_ram")
    if settings.image_memory_mode == "gpu" and offer.gpu_ram_gb < settings.image_full_gpu_min_vram_gb:
        errors.append("full_gpu_memory")
    if settings.vast_datacenter_only and offer.datacenter is not True:
        errors.append("datacenter")
    if not download_rate_allowed(offer, settings.vast_max_download_usd_per_tb):
        errors.append("download_rate")
    return errors
