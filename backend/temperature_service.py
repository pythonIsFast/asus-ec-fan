from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hardware.helper_client import HardwareError


class TemperatureReader(Protocol):
    def get_cpu_temperature(self) -> float | None: ...


class TemperatureService:
    """Reads CPU temperature through ordinary Linux thermal interfaces."""

    CPU_LABELS = ("package id", "tctl", "tdie", "cpu", "core 0")
    CPU_HWMON_NAMES = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")
    CPU_ZONE_TYPES = ("x86_pkg_temp", "acpitz", "cpu-thermal", "cpu_thermal")

    def __init__(
        self,
        hwmon_root: str | Path = "/sys/class/hwmon",
        thermal_root: str | Path = "/sys/class/thermal",
    ) -> None:
        self.hwmon_root = Path(hwmon_root)
        self.thermal_root = Path(thermal_root)

    @staticmethod
    def _read_millidegrees(path: Path) -> float | None:
        try:
            value = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        celsius = value / 1000.0
        return round(celsius, 1) if -20.0 <= celsius <= 150.0 else None

    def get_cpu_temperature(self) -> float | None:
        candidates: list[tuple[int, Path]] = []
        for input_path in self.hwmon_root.glob("hwmon*/temp*_input"):
            label_path = input_path.with_name(input_path.name.replace("_input", "_label"))
            try:
                label = label_path.read_text(encoding="utf-8").strip().lower()
            except OSError:
                label = ""
            try:
                hwmon_name = (input_path.parent / "name").read_text(encoding="utf-8").strip().lower()
            except OSError:
                hwmon_name = ""
            label_score = next(
                (index for index, name in enumerate(self.CPU_LABELS) if name in label), None
            )
            if label_score is not None:
                score = label_score
            elif hwmon_name in self.CPU_HWMON_NAMES:
                score = len(self.CPU_LABELS)
            else:
                continue
            candidates.append((score, input_path))

        for _, path in sorted(candidates, key=lambda item: item[0]):
            temperature = self._read_millidegrees(path)
            if temperature is not None:
                return temperature

        for zone in self.thermal_root.glob("thermal_zone*"):
            try:
                zone_type = (zone / "type").read_text(encoding="utf-8").strip().lower()
            except OSError:
                continue
            if zone_type in self.CPU_ZONE_TYPES:
                temperature = self._read_millidegrees(zone / "temp")
                if temperature is not None:
                    return temperature
        return None


class WindowsAsusTemperatureService:
    """Reads the temperature exported by the installed ASUS System Analysis DLL."""

    def __init__(self, backend: object) -> None:
        self._backend = backend

    def get_cpu_temperature(self) -> float | None:
        try:
            return self._backend.get_cpu_temperature()
        except (HardwareError, AttributeError):
            return None
