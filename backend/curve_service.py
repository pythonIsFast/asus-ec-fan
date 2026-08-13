from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from .fan_service import FanService, FanServiceError
from .temperature_service import TemperatureService


class CurveError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class CurvePoint:
    temperature: int
    percent: int

    def as_dict(self) -> dict[str, int]:
        return {"temperature": self.temperature, "percent": self.percent}


def validate_curve_points(raw_points: object) -> tuple[CurvePoint, ...]:
    if not isinstance(raw_points, list) or not 2 <= len(raw_points) <= 8:
        raise CurveError("INVALID_CURVE", "A curve requires 2 to 8 points")
    points: list[CurvePoint] = []
    for raw in raw_points:
        if not isinstance(raw, dict) or set(raw) != {"temperature", "percent"}:
            raise CurveError(
                "INVALID_CURVE",
                "Each curve point must contain only temperature and percent",
            )
        temperature = raw["temperature"]
        percent = raw["percent"]
        if isinstance(temperature, bool) or not isinstance(temperature, int):
            raise CurveError("INVALID_CURVE", "Curve temperatures must be integers")
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise CurveError("INVALID_CURVE", "Curve percentages must be integers")
        if not 20 <= temperature <= 100:
            raise CurveError("INVALID_CURVE", "Curve temperatures must be 20–100 °C")
        if not 1 <= percent <= 100:
            raise CurveError("INVALID_CURVE", "Curve percentages must be 1–100%")
        points.append(CurvePoint(temperature, percent))
    for previous, current in zip(points, points[1:]):
        if current.temperature <= previous.temperature:
            raise CurveError("INVALID_CURVE", "Curve temperatures must increase")
        if current.percent < previous.percent:
            raise CurveError("INVALID_CURVE", "Curve percentages must not decrease")
    return tuple(points)


def interpolate_curve(points: tuple[CurvePoint, ...], temperature: float) -> int:
    if temperature <= points[0].temperature:
        return points[0].percent
    if temperature >= points[-1].temperature:
        return points[-1].percent
    for lower, upper in zip(points, points[1:]):
        if temperature <= upper.temperature:
            fraction = (temperature - lower.temperature) / (
                upper.temperature - lower.temperature
            )
            return round(lower.percent + fraction * (upper.percent - lower.percent))
    return points[-1].percent


class CurveController:
    """Explicitly started userspace controller using only verified fixed-duty writes."""

    def __init__(
        self,
        fan_service: FanService,
        temperature_service: TemperatureService,
        interval_seconds: Callable[[], float],
    ) -> None:
        self._fan_service = fan_service
        self._temperature_service = temperature_service
        self._interval_seconds = interval_seconds
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = False
        self._fan = 0
        self._points: tuple[CurvePoint, ...] = ()
        self._name = "Custom curve"
        self._started_from_firmware = False
        self._target_percent: int | None = None
        self._temperature: float | None = None
        self._last_applied: str | None = None
        self._last_error: dict[str, str] | None = None

    def _snapshot(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "fan": self._fan,
            "name": self._name,
            "points": [point.as_dict() for point in self._points],
            "temperature": self._temperature,
            "target_percent": self._target_percent,
            "last_applied": self._last_applied,
            "last_error": self._last_error,
            "session_owned": self._started_from_firmware,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot()

    def _apply_once(self) -> None:
        temperature = self._temperature_service.get_cpu_temperature()
        if temperature is None:
            raise CurveError(
                "TEMPERATURE_UNAVAILABLE",
                "CPU temperature is unavailable; curve control was not applied",
                503,
            )
        with self._lock:
            points = self._points
            fan = self._fan
            previous_target = self._target_percent
        target = interpolate_curve(points, temperature)
        try:
            current = self._fan_service.get_fan(fan)
            if previous_target != target or current["mode"] != "manual":
                self._fan_service.set_manual(fan, target)
        except FanServiceError as exc:
            raise CurveError(exc.code, exc.message, exc.status_code) from exc
        with self._lock:
            self._temperature = temperature
            self._target_percent = target
            self._last_applied = datetime.now(UTC).isoformat()
            self._last_error = None

    def start(self, fan: object, raw_points: object, name: object = "Custom curve") -> dict[str, Any]:
        points = validate_curve_points(raw_points)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            raise CurveError("INVALID_CURVE_NAME", "Curve name must be 1–60 characters")
        self.stop(restore=True)
        try:
            current = self._fan_service.get_fan(fan)
        except FanServiceError as exc:
            raise CurveError(exc.code, exc.message, exc.status_code) from exc
        with self._lock:
            self._fan = current["id"]
            self._points = points
            self._name = name.strip()
            self._started_from_firmware = current["mode"] == "firmware"
            self._target_percent = None
            self._temperature = None
            self._last_applied = None
            self._last_error = None
            self._stop_event.clear()
        try:
            self._apply_once()
        except CurveError:
            if self._started_from_firmware:
                try:
                    self._fan_service.restore(current["id"])
                except FanServiceError:
                    pass
            raise
        with self._lock:
            self._active = True
            self._thread = threading.Thread(
                target=self._run, name="fan-curve-controller", daemon=True
            )
            self._thread.start()
            return self._snapshot()

    def _run(self) -> None:
        while not self._stop_event.wait(max(0.5, self._interval_seconds())):
            try:
                self._apply_once()
            except CurveError as exc:
                with self._lock:
                    self._active = False
                    self._last_error = {"error": exc.code, "message": exc.message}
                if self._started_from_firmware:
                    try:
                        self._fan_service.restore(self._fan)
                    except FanServiceError:
                        pass
                return

    def stop(self, *, restore: bool) -> dict[str, Any]:
        with self._lock:
            was_active = self._active
            should_restore = restore and was_active and self._started_from_firmware
            fan = self._fan
            self._active = False
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        if should_restore:
            try:
                self._fan_service.restore(fan)
            except FanServiceError as exc:
                raise CurveError(exc.code, exc.message, exc.status_code) from exc
        with self._lock:
            self._started_from_firmware = False
            return self._snapshot()
