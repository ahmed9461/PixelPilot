"""Marketplace policy shared by discovery, details and the final rental gate."""
from __future__ import annotations

from math import isfinite
import hashlib
import json
from pixelpilot.config import Settings
from pixelpilot.domain import GpuOffer
from pixelpilot.pricing import download_rate_allowed, nonnegative_number

NETWORK_LABELS = {"excellent": "ممتاز جدًا", "preferred": "مفضل", "standard": "الحد الافتراضي", "fallback": "احتياطي بطيء"}

def quote_fingerprint(offer: GpuOffer) -> str:
    return hashlib.sha256(json.dumps(offer.public_dict(), sort_keys=True, ensure_ascii=True).encode()).hexdigest()[:12]

def network_tier(offer: GpuOffer) -> str:
    down, up = offer.inet_down_mbps or 0, offer.inet_up_mbps or 0
    if down >= 3000 and up >= 1000: return "excellent"
    if down >= 2000 and up >= 1000: return "preferred"
    if down >= 1000 and up >= 500: return "standard"
    return "fallback"

def eligible(offer: GpuOffer, settings: Settings, *, network: bool = True) -> bool:
    if not isfinite(offer.price_per_hour) or not 0 < offer.price_per_hour <= min(0.60, settings.vast_max_price_usd_hour): return False
    if not isfinite(offer.gpu_ram_gb) or offer.gpu_ram_gb < settings.vast_min_gpu_ram_gb: return False
    if not isfinite(offer.reliability or 0) or (offer.reliability or 0) < settings.vast_min_reliability: return False
    if settings.vast_verified_only and offer.verified is not True: return False
    if not download_rate_allowed(offer, settings.vast_max_download_usd_per_tb): return False
    if network and (not isfinite(offer.inet_down_mbps or 0) or not isfinite(offer.inet_up_mbps or 0) or (offer.inet_down_mbps or 0) < settings.vast_min_inet_down_mbps or (offer.inet_up_mbps or 0) < settings.vast_min_inet_up_mbps): return False
    if offer.compute_cap is not None and offer.compute_cap < (800 if settings.model_dtype == 'bfloat16' else 700): return False
    raw = offer.raw or {}
    # Raw responses come from the live provider. Require all runtime resources;
    # cached cards intentionally omit raw data and are never sufficient to rent.
    if raw:
        if nonnegative_number(raw.get('num_gpus')) != 1: return False
        if (nonnegative_number(raw.get('direct_port_count')) or 0) < settings.vast_min_direct_ports: return False
        if (offer.disk_space_gb or 0) < settings.vast_disk_gb: return False
        if settings.vast_datacenter_only and raw.get('datacenter') is not True: return False
        offload = offer.gpu_ram_gb < settings.image_full_gpu_min_vram_gb or settings.image_memory_mode == 'offload'
        if offload and (nonnegative_number(raw.get('cpu_ram')) or 0) / 1000 < settings.vast_min_cpu_ram_gb: return False
    return True
