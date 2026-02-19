import pytest
from pydantic import ValidationError

from ws_src.models import RayCPUConfig


@pytest.mark.parametrize(
    ("memory", "expected"),
    [
        ("8g", "8g"),
        ("01g", "01g"),
        ("16G", "16g"),
        ("512m", "512m"),
    ],
)
def test_memory_validation_accepts_valid_values_and_normalizes(
    memory: str, expected: str
):
    config = RayCPUConfig(memory=memory)
    assert config.memory == expected


@pytest.mark.parametrize(
    "memory",
    ["0g", "0m", "-1g", "abc", "8", "g8", ""],
)
def test_memory_validation_rejects_invalid_values(memory: str):
    with pytest.raises(ValidationError):
        RayCPUConfig(memory=memory)
