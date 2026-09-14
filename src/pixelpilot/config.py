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
    vast_max_price_usd_hour: float = 1.50
    vast_default_limit: int = 8
    vast_verified_only: bool = True
    vast_datacenter_only: bool = False
    vast_min_direct_ports: int = 2
    vast_min_inet_down_mbps: float = 100.0
    vast_cancel_unavailable: bool = True
    vast_auto_destroy_on_provision_failure: bool = False

    # Runtime bundle source copied/cloned into ephemeral GPU instances.
    pixelpilot_repo_url: str = ""
    pixelpilot_repo_ref: str = "main"

    # Hugging Face; only forwarded to an instance at rent-time, never logged.
    hf_token: str = ""

    # Worker / ComfyUI inside Vast. The Worker is exposed directly through the
    # mapped Vast TCP port and authenticates every request with a bearer token,
    # so the controller talks plain HTTP to that port (no implicit TLS proxy).
    worker_proxy_port: int = 8190
    worker_internal_port: int = 18190
    worker_use_https: bool = False
    worker_verify_tls: bool = False
    worker_request_timeout_seconds: int = 60
    worker_generation_timeout_seconds: int = 900
    comfy_port: int = 8188
    comfy_ready_timeout_seconds: int = 1200
    provision_ready_timeout_seconds: int = 1800
    provision_poll_seconds: float = 5.0
    comfyui_ref: str = "v0.35.0"
    workflow_path: Path = Path("./resources/workflows/flux_krea_api.json")

    # Generation safety limits
    generation_max_batch: int = 4
    generation_default_steps: int = 20
    generation_max_steps: int = 40

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
    def reliability_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("VAST_MIN_RELIABILITY must be between 0 and 1")
        return value

    @field_validator("vast_default_limit", "vast_min_gpu_ram_gb", "generation_max_batch")
    @classmethod
    def positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be > 0")
        return value

    @field_validator("vast_disk_gb")
    @classmethod
    def disk_large_enough_for_full_krea(cls, value: int) -> int:
        if value < 70:
            raise ValueError("VAST_DISK_GB must be >= 70 for the full Krea profile")
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
        if not self.hf_token:
            missing.append("HF_TOKEN")
        if not self.pixelpilot_repo_url and not self.vast_template_hash:
            missing.append("PIXELPILOT_REPO_URL or VAST_TEMPLATE_HASH")
        if missing:
            raise RuntimeError("Cannot rent until configured: " + ", ".join(missing))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
