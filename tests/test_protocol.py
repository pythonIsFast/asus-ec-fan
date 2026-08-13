import pytest

from hardware.protocol import (
    percent_to_pwm,
    rpm_from_bytes,
    validate_fan_index,
    validate_percent,
)


@pytest.mark.parametrize(
    ("percent", "pwm"), [(1, 3), (50, 128), (60, 153), (100, 255)]
)
def test_percent_to_pwm(percent, pwm):
    assert percent_to_pwm(percent) == pwm


@pytest.mark.parametrize("percent", [0, 101, -1, 2.5, "60", True, None])
def test_percent_validation_rejects_invalid_values(percent):
    with pytest.raises(ValueError):
        validate_percent(percent)


def test_rpm_byte_calculation():
    assert rpm_from_bytes(0x0A, 0x0F) == 3850


@pytest.mark.parametrize("values", [(-1, 0), (256, 0), (0, 256), (True, 0)])
def test_rpm_byte_validation(values):
    with pytest.raises(ValueError):
        rpm_from_bytes(*values)


def test_fan_index_validation():
    assert validate_fan_index(0, 1) == 0
    with pytest.raises(ValueError):
        validate_fan_index(1, 1)
    with pytest.raises(ValueError):
        validate_fan_index(True, 1)
