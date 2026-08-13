from __future__ import annotations

import threading
from typing import Any

from hardware.helper_client import FanHardwareBackend, HardwareError
from hardware.protocol import validate_fan_index, validate_percent


class FanServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class FanService:
    def __init__(
        self,
        backend: FanHardwareBackend,
        *,
        model: str,
        writes_allowed: bool,
        mock_mode: bool = False,
    ) -> None:
        self.backend = backend
        self.model = model
        self.writes_allowed = writes_allowed
        self.mock_mode = mock_mode
        self._lock = threading.RLock()
        self._session_owned_fans: set[int] = set()
        self._manual_percent: dict[int, int] = {}

    def _fan_count(self) -> int:
        try:
            count = self.backend.get_fan_count()
        except HardwareError as exc:
            raise FanServiceError(exc.code, exc.message, 503) from exc
        if not 1 <= count <= 8:
            raise FanServiceError("INVALID_FAN_COUNT", "EC returned an invalid fan count", 503)
        return count

    def _validate_fan(self, fan_index: object) -> int:
        try:
            return validate_fan_index(fan_index, self._fan_count())
        except ValueError as exc:
            raise FanServiceError("INVALID_FAN", str(exc)) from exc

    @staticmethod
    def _hardware_error(exc: HardwareError) -> FanServiceError:
        return FanServiceError(exc.code, exc.message, 503)

    def device_status(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "supported": self.writes_allowed or self.mock_mode,
            "writes_allowed": self.writes_allowed,
            "mock_mode": self.mock_mode,
            "backend": self.backend.backend_name,
        }

    def get_ec_status(self) -> dict[str, Any]:
        with self._lock:
            try:
                status = self.backend.get_status()
            except HardwareError as exc:
                raise self._hardware_error(exc) from exc
            raw_status = status.get("status")
            result = {
                "status": int(raw_status) if isinstance(raw_status, int) else None,
                "obf": bool(status["obf"]) if "obf" in status else None,
                "ibf": bool(status["ibf"]) if "ibf" in status else None,
            }
            if "source" in status:
                result["source"] = str(status["source"])
            return result

    def _get_validated_fan(self, fan: int) -> dict[str, Any]:
        try:
            rpm = self.backend.get_rpm(fan)
            manual = self.backend.get_test_mode(fan)
        except HardwareError as exc:
            raise self._hardware_error(exc) from exc
        return {
            "id": fan,
            "rpm": rpm,
            "mode": "unknown" if manual is None else ("manual" if manual else "firmware"),
            "test_mode": manual,
            "percent": self._manual_percent.get(fan) if manual else None,
            "session_owned": fan in self._session_owned_fans,
        }

    def get_fan(self, fan_index: object) -> dict[str, Any]:
        with self._lock:
            return self._get_validated_fan(self._validate_fan(fan_index))

    def get_fans(self) -> list[dict[str, Any]]:
        with self._lock:
            count = self._fan_count()
            return [self._get_validated_fan(index) for index in range(count)]

    def set_manual(self, fan_index: object, percent: object) -> dict[str, Any]:
        if not self.writes_allowed:
            raise FanServiceError(
                "UNSUPPORTED_HARDWARE",
                f"Manual fan writes are blocked for model {self.model}",
                403,
            )
        try:
            value = validate_percent(percent)
        except ValueError as exc:
            raise FanServiceError("INVALID_PERCENT", str(exc)) from exc
        with self._lock:
            fan = self._validate_fan(fan_index)
            try:
                was_manual = self.backend.get_test_mode(fan)
            except HardwareError as exc:
                raise self._hardware_error(exc) from exc
            if was_manual is None:
                raise FanServiceError(
                    "MODE_BASELINE_REQUIRED",
                    "The ASUS Windows interface cannot read test mode. Explicitly restore "
                    "firmware control once before enabling manual control.",
                    409,
                )
            if not was_manual:
                self._session_owned_fans.add(fan)
            try:
                self.backend.set_percent(fan, value)
                enabled = self.backend.get_test_mode(fan)
            except HardwareError as exc:
                if not was_manual:
                    try:
                        self.backend.restore(fan)
                    except HardwareError:
                        pass
                    else:
                        self._session_owned_fans.discard(fan)
                raise self._hardware_error(exc) from exc
            if not enabled:
                try:
                    self.backend.restore(fan)
                except HardwareError:
                    pass
                else:
                    self._session_owned_fans.discard(fan)
                raise FanServiceError(
                    "EC_VERIFY_FAILED",
                    "The EC did not confirm manual fan control",
                    503,
                )
            self._manual_percent[fan] = value
            return {
                "ok": True,
                "fan": fan,
                "mode": "manual",
                "percent": value,
                "verified": self.backend.mode_readback_available,
            }

    def restore(self, fan_index: object) -> dict[str, Any]:
        if not self.writes_allowed:
            raise FanServiceError(
                "UNSUPPORTED_HARDWARE",
                f"Fan writes are blocked for model {self.model}",
                403,
            )
        with self._lock:
            fan = self._validate_fan(fan_index)
            try:
                self.backend.restore(fan)
                still_manual = self.backend.get_test_mode(fan)
            except HardwareError as exc:
                raise self._hardware_error(exc) from exc
            if still_manual:
                raise FanServiceError(
                    "EC_VERIFY_FAILED",
                    "The EC still reports manual test mode after restore",
                    503,
                )
            self._session_owned_fans.discard(fan)
            self._manual_percent.pop(fan, None)
            return {
                "ok": True,
                "fan": fan,
                "mode": "firmware",
                "verified": self.backend.mode_readback_available,
            }

    def restore_session_owned(self) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        with self._lock:
            for fan in sorted(self._session_owned_fans):
                try:
                    self.backend.restore(fan)
                except HardwareError as exc:
                    failures.append({"fan": fan, "error": exc.code, "message": exc.message})
                else:
                    self._manual_percent.pop(fan, None)
            if not failures:
                self._session_owned_fans.clear()
            else:
                failed_fans = {item["fan"] for item in failures}
                self._session_owned_fans.intersection_update(failed_fans)
        return failures
