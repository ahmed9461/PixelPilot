import pytest
from pydantic import ValidationError

from pixelpilot.config import Settings


def test_reliability_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_min_reliability=1.1)


def test_runtime_validation_missing():
    settings = Settings(_env_file=None, telegram_bot_token="", owner_telegram_id=0, vast_api_key="")
    with pytest.raises(RuntimeError):
        settings.validate_runtime()


def test_qwen_economy_profile_defaults():
    settings = Settings(_env_file=None)
    assert settings.model_id == "Qwen/Qwen2.5-Omni-7B"
    assert settings.vast_min_gpu_ram_gb == 48
    assert settings.vast_disk_gb == 80
    assert settings.vast_max_price_usd_hour == 0.80
    assert settings.model_max_len == 8192


def test_qwen_economy_profile_rejects_small_gpu():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_min_gpu_ram_gb=32)


def test_qwen_economy_profile_accepts_48gb_gpu():
    settings = Settings(_env_file=None, vast_min_gpu_ram_gb=48)
    assert settings.vast_min_gpu_ram_gb == 48
