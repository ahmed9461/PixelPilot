from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class InstancePhase(StrEnum):
    NONE = "none"
    RENTING = "renting"
    BOOTING = "booting"
    PROVISIONING = "provisioning"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DESTROYING = "destroying"
    ERROR = "error"


@dataclass(slots=True, frozen=True)
class GpuOffer:
    offer_id: int
    gpu_name: str
    gpu_ram_gb: float
    price_per_hour: float
    reliability: float | None
    dlperf: float | None
    location: str | None = None
    inet_down_mbps: float | None = None
    disk_space_gb: float | None = None
    verified: bool | None = None
    raw: dict[str, Any] | None = None

    @property
    def display_name(self) -> str:
        rel = "?" if self.reliability is None else f"{self.reliability * 100:.1f}%"
        return (
            f"{self.gpu_name} • {self.gpu_ram_gb:.0f}GB • "
            + f"$ {self.price_per_hour:.3f}/h • R {rel}"
        )

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data


@dataclass(slots=True, frozen=True)
class InstanceRef:
    instance_id: int
    status: str
    public_ip: str | None = None
    mapped_port: int | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class ReferenceImage:
    data: bytes
    mime_type: str = "image/jpeg"


@dataclass(slots=True, frozen=True)
class GeneratedImage:
    data: bytes
    mime_type: str
    seed: int
    width: int
    height: int
    model: str
    reference_count: int = 0
    prompt_enhanced: bool = False
    enhancer_model: str | None = None
    enhancer_ratio: str | None = None
    enhancer_fallback: bool = False
