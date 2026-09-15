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


class GenerationStatus(StrEnum):
    CREATED = "created"
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
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
        return f"{self.gpu_name} • {self.gpu_ram_gb:.0f}GB • ${self.price_per_hour:.3f}/h • R {rel}"

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
class GenerationSpec:
    prompt: str
    width: int = 1024
    height: int = 1024
    seed: int = 0
    steps: int = 28
    batch_size: int = 1
    preset: str = "raw"
    quality_profile: str = "flux2_balanced"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ImageRef:
    filename: str
    subfolder: str = ""
    image_type: str = "output"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GenerationResult:
    generation_id: int
    prompt_id: str
    spec: GenerationSpec
    images: list[ImageRef]
