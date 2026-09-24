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


def test_qwen_image_profile_defaults():
    settings = Settings(_env_file=None)
    assert settings.model_id == "Qwen/Qwen-Image-2.1"
    assert settings.vast_min_gpu_ram_gb == 24
    assert settings.vast_preferred_gpu_ram_gb == 48
    assert settings.vast_disk_gb == 100
    assert settings.vast_min_cpu_ram_gb == 64
    assert settings.vast_default_limit == 8
    assert settings.vast_search_pool_limit == 64
    assert settings.inference_probe_timeout_seconds == 5.0
    assert settings.vast_status_timeout_seconds == 8.0
    assert settings.vast_max_price_usd_hour == 0.50
    assert settings.model_dtype == "bfloat16"
    assert settings.image_memory_mode == "auto"
    assert settings.image_default_steps == 40
    assert settings.image_max_reference_images == 10
    assert settings.prompt_enhancer_t2i_id == "Qwen/Qwen-Image-2.1-PE-T2I"
    assert settings.prompt_enhancer_i2i_id == "Qwen/Qwen-Image-2.1-PE-I2I"
    assert settings.prompt_enhancer_fail_open is True


def test_qwen_image_profile_rejects_gpu_below_24gb():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_min_gpu_ram_gb=16)


def test_qwen_image_profile_accepts_24gb_gpu():
    settings = Settings(_env_file=None, vast_min_gpu_ram_gb=24)
    assert settings.vast_min_gpu_ram_gb == 24


def test_memory_mode_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, image_memory_mode="magic")


def test_reference_limit_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, image_max_reference_images=11)


def test_qwen_image_profile_rejects_small_disk():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_disk_gb=60)


def test_qwen_image_profile_rejects_low_host_ram():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_min_cpu_ram_gb=48)



def test_runtime_timeouts_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, inference_probe_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_status_timeout_seconds=0)
