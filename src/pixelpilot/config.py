from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Controller / Telegram
    telegram_bot_token: str = ""
    owner_telegram_id: int = 0
    database_path: Path = Path("./pixelpilot.sqlite3")
    log_level: str = "INFO"

    # Vast.ai controller credentials and offer policy
    vast_api_key: str = ""
    vast_template_hash: str | None = None
    vast_docker_image: str = "vastai/pytorch:@vastai-automatic-tag"
    vast_disk_gb: int = 100
    # Qwen-Image-2.1 can run on 24 GB with CPU offload. 48 GB+ is preferred
    # because the BF16 checkpoint is roughly 33 GB before runtime overhead.
    vast_min_gpu_ram_gb: int = 24
    vast_preferred_gpu_ram_gb: int = 48
    # CPU offload keeps large model components in host memory on 24 GB GPUs.
    vast_min_cpu_ram_gb: int = 48
    vast_min_reliability: float = 0.98
    vast_max_price_usd_hour: float = 0.50
    vast_default_limit: int = 8
    vast_search_pool_limit: int = 64
    vast_verified_only: bool = True
    vast_datacenter_only: bool = False
    vast_min_direct_ports: int = 1
    vast_min_inet_down_mbps: float = 100.0
    vast_cancel_unavailable: bool = True
    vast_auto_destroy_on_provision_failure: bool = False

    # Runtime bundle source copied/cloned into ephemeral GPU instances.
    pixelpilot_repo_url: str = ""
    pixelpilot_repo_ref: str = "main"

    # Optional Hugging Face read token. Qwen-Image-2.1 is public, but an
    # authenticated token can improve Hub download reliability/rate limits.
    hf_token: str = ""

    # Qwen-Image-2.1 runtime.
    model_id: str = "Qwen/Qwen-Image-2.1"
    model_dtype: str = "bfloat16"
    image_memory_mode: str = "auto"  # auto | gpu | offload
    image_full_gpu_min_vram_gb: int = 48
    image_vae_tiling: bool = True
    image_vae_slicing: bool = True
    image_default_steps: int = 40
    image_max_reference_images: int = 10
    image_max_upload_mb: int = 25
    prompt_enhancer_t2i_id: str = "Qwen/Qwen-Image-2.1-PE-T2I"
    prompt_enhancer_i2i_id: str = "Qwen/Qwen-Image-2.1-PE-I2I"

    # Public authenticated image inference endpoint.
    inference_port: int = 8190
    inference_use_https: bool = False
    inference_verify_tls: bool = False
    inference_request_timeout_seconds: int = 3600
    inference_probe_timeout_seconds: float = 5.0
    vast_status_timeout_seconds: float = 8.0
    inference_ready_timeout_seconds: int = 2400
    provision_poll_seconds: float = 5.0

    # Cost guard. Auto-destroy is disabled unless explicitly configured.
    cost_guard_warn_minutes: int = 30
    cost_guard_auto_destroy_minutes: int = 0
    cost_guard_poll_seconds: int = 60

    @field_validator("owner_telegram_id")
    @classmethod
    def owner_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("OWNER_TELEGRAM_ID must be >= 0")
        return value

    @field_validator("vast_min_reliability")
    @classmethod
    def fraction_range(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("VAST_MIN_RELIABILITY must be > 0 and <= 1")
        return value

    @field_validator("vast_max_price_usd_hour")
    @classmethod
    def positive_price_cap(cls, value: float) -> float:
        if not 0 < value <= 0.50:
            raise ValueError("VAST_MAX_PRICE_USD_HOUR must be > 0 and <= $0.50")
        return value

    @field_validator(
        "vast_default_limit",
        "vast_search_pool_limit",
        "vast_min_gpu_ram_gb",
        "vast_preferred_gpu_ram_gb",
        "vast_min_cpu_ram_gb",
        "image_full_gpu_min_vram_gb",
        "image_default_steps",
        "image_max_reference_images",
        "image_max_upload_mb",
        "inference_port",
        "inference_request_timeout_seconds",
        "inference_ready_timeout_seconds",
    )
    @classmethod
    def positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be > 0")
        return value

    @field_validator(
        "inference_probe_timeout_seconds",
        "vast_status_timeout_seconds",
        "provision_poll_seconds",
    )
    @classmethod
    def positive_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout values must be > 0")
        return value

    @field_validator("vast_disk_gb")
    @classmethod
    def disk_large_enough_for_qwen_image(cls, value: int) -> int:
        if value < 70:
            raise ValueError("VAST_DISK_GB must be >= 70 for Qwen-Image-2.1 and runtime caches")
        return value

    @field_validator("vast_min_gpu_ram_gb")
    @classmethod
    def vram_large_enough_for_qwen_image(cls, value: int) -> int:
        if value < 24:
            raise ValueError("VAST_MIN_GPU_RAM_GB must be >= 24 for the supported Qwen-Image-2.1 profile")
        return value

    @field_validator("vast_preferred_gpu_ram_gb")
    @classmethod
    def preferred_vram_not_too_small(cls, value: int) -> int:
        if value < 24:
            raise ValueError("VAST_PREFERRED_GPU_RAM_GB must be >= 24")
        return value

    @field_validator("vast_min_cpu_ram_gb")
    @classmethod
    def host_ram_large_enough_for_offload(cls, value: int) -> int:
        if value < 48:
            raise ValueError("VAST_MIN_CPU_RAM_GB must be >= 48 for the 24 GB offload profile")
        return value

    @field_validator("image_memory_mode")
    @classmethod
    def memory_mode_supported(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "gpu", "offload"}:
            raise ValueError("IMAGE_MEMORY_MODE must be auto, gpu, or offload")
        return normalized

    @field_validator("model_dtype")
    @classmethod
    def dtype_supported(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"bfloat16", "float16"}:
            raise ValueError("MODEL_DTYPE must be bfloat16 or float16")
        return normalized

    @field_validator("image_default_steps")
    @classmethod
    def steps_range(cls, value: int) -> int:
        if not 1 <= value <= 80:
            raise ValueError("IMAGE_DEFAULT_STEPS must be between 1 and 80")
        return value

    @field_validator("image_max_reference_images")
    @classmethod
    def reference_limit(cls, value: int) -> int:
        if not 1 <= value <= 10:
            raise ValueError("IMAGE_MAX_REFERENCE_IMAGES must be between 1 and 10")
        return value

    def validate_runtime(self) -> None:
        missing: list[str] = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.owner_telegram_id:
            missing.append("OWNER_TELEGRAM_ID")
        if not self.vast_api_key:
            missing.append("VAST_API_KEY")
        if missing:
            raise RuntimeError("Missing required settings: " + ", ".join(missing))

    def validate_rent_ready(self) -> None:
        missing: list[str] = []
        if not self.pixelpilot_repo_url and not self.vast_template_hash:
            missing.append("PIXELPILOT_REPO_URL or VAST_TEMPLATE_HASH")
        if not self.model_id:
            missing.append("MODEL_ID")
        if not self.vast_cancel_unavailable:
            missing.append("VAST_CANCEL_UNAVAILABLE=true (required for safe on-demand rent)")
        if missing:
            raise RuntimeError("Cannot rent until configured: " + ", ".join(missing))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
