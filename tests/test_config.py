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


def test_qwen3_vl_whisper_profile_defaults():
    settings = Settings(_env_file=None)
    assert settings.model_id == "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8"
    assert settings.vast_min_gpu_ram_gb == 48
    assert settings.vast_disk_gb == 100
    assert settings.vast_max_price_usd_hour == 0.50
    assert settings.model_max_len == 16384
    assert settings.model_gpu_memory_utilization == 0.82
    assert settings.whisper_model == "turbo"
    assert settings.whisper_device == "auto"
    assert settings.vllm_internal_port == 8191


def test_qwen3_vl_profile_rejects_small_gpu():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_min_gpu_ram_gb=32)


def test_qwen3_vl_profile_accepts_48gb_gpu():
    settings = Settings(_env_file=None, vast_min_gpu_ram_gb=48)
    assert settings.vast_min_gpu_ram_gb == 48


def test_price_cap_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_max_price_usd_hour=0)



def test_whisper_device_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, whisper_device="tpu")


def test_qwen3_vl_profile_rejects_small_disk():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_disk_gb=80)
