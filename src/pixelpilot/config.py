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
    vast_min_gpu_ram_gb: int = 48
    vast_min_reliability: float = 0.98
    vast_max_price_usd_hour: float = 0.50
    vast_default_limit: int = 8
    vast_verified_only: bool = True
    vast_datacenter_only: bool = False
    vast_min_direct_ports: int = 1
    vast_min_inet_down_mbps: float = 100.0
    vast_cancel_unavailable: bool = True
    vast_auto_destroy_on_provision_failure: bool = False

    # Runtime bundle source copied/cloned into ephemeral GPU instances.
    pixelpilot_repo_url: str = ""
    pixelpilot_repo_ref: str = "main"

    # Optional Hugging Face read token. The Qwen3-VL FP8 checkpoint is public,
    # but authenticated Hub access can improve download reliability/rate limits.
    hf_token: str = ""

    # Vision-language model served by vLLM. Qwen3-VL handles text, images and
    # video; speech is transcribed by Whisper and then passed into Qwen3-VL.
    model_id: str = "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8"
    model_dtype: str = "auto"
    model_max_len: int = 16384
    model_max_output_tokens: int = 2048
    model_gpu_memory_utilization: float = 0.82
    model_tensor_parallel_size: int = 1
    model_limit_images: int = 1
    model_limit_audio: int = 1
    model_limit_videos: int = 1

    # Speech recognition sidecar on the same temporary GPU instance.
    whisper_model: str = "turbo"
    whisper_device: str = "auto"

    # Public mapped gateway endpoint. vLLM itself is bound only to localhost
    # on a second internal port; the gateway adds Whisper transcription.
    inference_port: int = 8190
    vllm_internal_port: int = 8191
    inference_use_https: bool = False
    inference_verify_tls: bool = False
    inference_request_timeout_seconds: int = 600
    inference_ready_timeout_seconds: int = 1800
    provision_poll_seconds: float = 5.0

    # Telegram chat session. History exists only in controller memory and is
    # never written to SQLite; /new clears it immediately.
    chat_history_messages: int = 10
    chat_max_media_mb: int = 20

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

    @field_validator("vast_min_reliability", "model_gpu_memory_utilization")
    @classmethod
    def fraction_range(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("value must be > 0 and <= 1")
        return value

    @field_validator("vast_max_price_usd_hour")
    @classmethod
    def positive_price_cap(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("VAST_MAX_PRICE_USD_HOUR must be > 0")
        return value

    @field_validator(
        "vast_default_limit",
        "vast_min_gpu_ram_gb",
        "model_max_len",
        "model_max_output_tokens",
        "model_tensor_parallel_size",
        "model_limit_images",
        "model_limit_audio",
        "model_limit_videos",
        "inference_port",
        "vllm_internal_port",
        "inference_request_timeout_seconds",
        "inference_ready_timeout_seconds",
        "chat_history_messages",
        "chat_max_media_mb",
    )
    @classmethod
    def positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be > 0")
        return value

    @field_validator("vast_disk_gb")
    @classmethod
    def disk_large_enough_for_qwen3_vl(cls, value: int) -> int:
        if value < 90:
            raise ValueError("VAST_DISK_GB must be >= 90 for Qwen3-VL 30B FP8 + Whisper")
        return value

    @field_validator("vast_min_gpu_ram_gb")
    @classmethod
    def vram_large_enough_for_qwen3_vl(cls, value: int) -> int:
        if value < 48:
            raise ValueError("VAST_MIN_GPU_RAM_GB must be >= 48 for the supported Qwen3-VL 30B FP8 profile")
        return value

    @field_validator("whisper_device")
    @classmethod
    def whisper_device_supported(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "cuda", "cpu"}:
            raise ValueError("WHISPER_DEVICE must be auto, cuda, or cpu")
        return normalized

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
        if missing:
            raise RuntimeError("Cannot rent until configured: " + ", ".join(missing))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
