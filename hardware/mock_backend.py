"""Deterministic, hardware-safe backend for tests and UI development."""

from __future__ import annotations

from typing import Any

from .helper_client import FanHardwareBackend, HardwareError
from .protocol import validate_fan_index, validate_percent


class MockFanBackend(FanHardwareBackend):
    backend_name = "Mock hardware"

    def __init__(self, fan_count: int = 1, rpm: int = 3800) -> None:
        if not 1 <= fan_count <= 8:
            raise ValueError("Mock fan count must be between 1 and 8")
        self.fan_count = fan_count
        self.rpms = [rpm for _ in range(fan_count)]
        self.test_modes = [False for _ in range(fan_count)]
        self.percents: list[int | None] = [None for _ in range(fan_count)]
        self.operations: list[tuple[Any, ...]] = []
        self.failure: HardwareError | None = None

    def _check_failure(self) -> None:
        if self.failure is not None:
            raise self.failure

    def _validate(self, fan_index: int) -> int:
        return validate_fan_index(fan_index, self.fan_count)

    def get_status(self) -> dict[str, Any]:
        self._check_failure()
        self.operations.append(("status",))
        return {"ok": True, "mock": True, "status": 0, "obf": False, "ibf": False}

    def get_fan_count(self) -> int:
        self._check_failure()
        self.operations.append(("fan-count",))
        return self.fan_count

    def get_rpm(self, fan_index: int) -> int:
        self._check_failure()
        fan = self._validate(fan_index)
        self.operations.append(("rpm", fan))
        return self.rpms[fan]

    def get_test_mode(self, fan_index: int) -> bool:
        self._check_failure()
        fan = self._validate(fan_index)
        self.operations.append(("test-mode", fan))
        return self.test_modes[fan]

    def set_percent(self, fan_index: int, percent: int) -> None:
        self._check_failure()
        fan = self._validate(fan_index)
        value = validate_percent(percent)
        self.operations.extend(
            [("select", fan), ("enable-test-mode", fan), ("set-pwm", fan, value)]
        )
        self.test_modes[fan] = True
        self.percents[fan] = value
        self.rpms[fan] = 1200 + value * 35

    def restore(self, fan_index: int) -> None:
        self._check_failure()
        fan = self._validate(fan_index)
        self.operations.extend(
            [("select", fan), ("disable-test-mode", fan), ("set-pwm", fan, 0)]
        )
        self.test_modes[fan] = False
        self.percents[fan] = None
        self.rpms[fan] = 3800
