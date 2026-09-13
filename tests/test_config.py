import pytest
from pydantic import ValidationError

from pixelpilot.config import Settings


def test_reliability_validation():
    with pytest.raises(ValidationError):
        Settings(vast_min_reliability=1.1)


def test_runtime_validation_missing():
    s = Settings(_env_file=None, telegram_bot_token="", owner_telegram_id=0, vast_api_key="")
    with pytest.raises(RuntimeError):
        s.validate_runtime()
