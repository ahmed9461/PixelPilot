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


def test_qwen_profile_defaults():
    settings = Settings(_env_file=None)
    assert settings.model_id == "Qwen/Qwen3-Omni-30B-A3B-Instruct"
    assert settings.vast_min_gpu_ram_gb >= 80
    assert settings.vast_disk_gb >= 120


def test_qwen_profile_rejects_small_gpu():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vast_min_gpu_ram_gb=48)
