"""Pure validation and conversion helpers for the verified EC protocol."""


def validate_fan_index(fan_index: object, fan_count: int) -> int:
    if isinstance(fan_index, bool) or not isinstance(fan_index, int):
        raise ValueError("Fan index must be an integer")
    if fan_count < 1 or fan_index < 0 or fan_index >= fan_count:
        raise ValueError(f"Fan index {fan_index} is outside the available range")
    return fan_index


def validate_percent(percent: object) -> int:
    if isinstance(percent, bool) or not isinstance(percent, int):
        raise ValueError("Fan percentage must be an integer")
    if percent < 1 or percent > 100:
        raise ValueError("Fan percentage must be between 1 and 100")
    return percent


def percent_to_pwm(percent: object) -> int:
    value = validate_percent(percent)
    return (value * 255 + 50) // 100


def rpm_from_bytes(low: object, high: object) -> int:
    for name, value in (("low", low), ("high", high)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError(f"RPM {name} byte must be an integer from 0 to 255")
    return (high << 8) | low
