from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Literal


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


MediaKind = Literal["image", "audio", "video"]


@dataclass(slots=True, frozen=True)
class MediaInput:
    kind: MediaKind
    data: bytes
    mime_type: str

    def data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"

    def to_openai_part(self) -> dict[str, Any]:
        url = self.data_url()
        if self.kind == "image":
            return {"type": "image_url", "image_url": {"url": url}}
        if self.kind == "audio":
            return {"type": "audio_url", "audio_url": {"url": url}}
        if self.kind == "video":
            # Keep visual tokens comfortably inside PixelPilot's 8K context.
            # Qwen/vLLM supports an explicit frame cap on video_url inputs.
            return {
                "type": "video_url",
                "video_url": {"url": url, "num_frames": 24},
            }
        raise ValueError(f"Unsupported media kind: {self.kind}")


@dataclass(slots=True, frozen=True)
class UserInput:
    text: str | None = None
    media: tuple[MediaInput, ...] = ()

    def to_openai_message(self) -> dict[str, Any]:
        """Build exactly one user message without silently rewriting its content."""
        if not self.media:
            return {"role": "user", "content": self.text or ""}

        content: list[dict[str, Any]] = [item.to_openai_part() for item in self.media]
        if self.text is not None and self.text != "":
            content.append({"type": "text", "text": self.text})
        return {"role": "user", "content": content}


@dataclass(slots=True, frozen=True)
class InferenceResult:
    text: str
    model: str
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
