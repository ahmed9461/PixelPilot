from __future__ import annotations

from dataclasses import dataclass

from pixelpilot.db import Database


STANDARD_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
    "3:2": (1216, 832),
    "2:3": (832, 1216),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
}

HIGH_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}

ASPECT_RATIOS = tuple(STANDARD_SIZES)
QUALITY_MODES = ("standard", "high")
PROMPT_MODES = ("original", "qwen")
STEP_CHOICES = (20, 30, 40, 50)

DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_QUALITY = "standard"
DEFAULT_PROMPT_MODE = "original"
DEFAULT_STEPS = 40


@dataclass(slots=True, frozen=True)
class ImageSettingsState:
    aspect_ratio: str
    quality: str
    steps: int
    prompt_mode: str

    @property
    def size(self) -> tuple[int, int]:
        table = HIGH_SIZES if self.quality == "high" else STANDARD_SIZES
        return table[self.aspect_ratio]

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    @property
    def enhance_prompt(self) -> bool:
        return self.prompt_mode == "qwen"


async def ensure_defaults(db: Database) -> None:
    current = await db.get_many(
        (
            "image.settings.aspect_ratio",
            "image.settings.quality",
            "image.settings.steps",
            "image.settings.prompt_mode",
        )
    )
    missing: dict[str, object] = {}
    if "image.settings.aspect_ratio" not in current:
        missing["image.settings.aspect_ratio"] = DEFAULT_ASPECT_RATIO
    if "image.settings.quality" not in current:
        missing["image.settings.quality"] = DEFAULT_QUALITY
    if "image.settings.steps" not in current:
        missing["image.settings.steps"] = DEFAULT_STEPS
    if "image.settings.prompt_mode" not in current:
        missing["image.settings.prompt_mode"] = DEFAULT_PROMPT_MODE
    await db.set_many(missing)


async def get_state(db: Database) -> ImageSettingsState:
    values = await db.get_many(
        (
            "image.settings.aspect_ratio",
            "image.settings.quality",
            "image.settings.steps",
            "image.settings.prompt_mode",
        )
    )
    aspect = str(values.get("image.settings.aspect_ratio", DEFAULT_ASPECT_RATIO))
    quality = str(values.get("image.settings.quality", DEFAULT_QUALITY))
    prompt_mode = str(values.get("image.settings.prompt_mode", DEFAULT_PROMPT_MODE))
    try:
        steps = int(values.get("image.settings.steps", DEFAULT_STEPS))
    except (TypeError, ValueError):
        steps = DEFAULT_STEPS

    if aspect not in ASPECT_RATIOS:
        aspect = DEFAULT_ASPECT_RATIO
    if quality not in QUALITY_MODES:
        quality = DEFAULT_QUALITY
    if prompt_mode not in PROMPT_MODES:
        prompt_mode = DEFAULT_PROMPT_MODE
    if steps not in STEP_CHOICES:
        steps = DEFAULT_STEPS
    return ImageSettingsState(
        aspect_ratio=aspect,
        quality=quality,
        steps=steps,
        prompt_mode=prompt_mode,
    )


async def set_aspect_ratio(db: Database, value: str) -> None:
    if value not in ASPECT_RATIOS:
        raise ValueError("Unsupported aspect ratio")
    await db.set("image.settings.aspect_ratio", value)


async def set_quality(db: Database, value: str) -> None:
    if value not in QUALITY_MODES:
        raise ValueError("Unsupported quality")
    await db.set("image.settings.quality", value)


async def set_prompt_mode(db: Database, value: str) -> None:
    if value not in PROMPT_MODES:
        raise ValueError("Unsupported prompt mode")
    await db.set("image.settings.prompt_mode", value)


async def set_steps(db: Database, value: int) -> None:
    if value not in STEP_CHOICES:
        raise ValueError("Unsupported step count")
    await db.set("image.settings.steps", value)


async def reset(db: Database) -> None:
    await db.set_many(
        {
            "image.settings.aspect_ratio": DEFAULT_ASPECT_RATIO,
            "image.settings.quality": DEFAULT_QUALITY,
            "image.settings.steps": DEFAULT_STEPS,
            "image.settings.prompt_mode": DEFAULT_PROMPT_MODE,
        }
    )
