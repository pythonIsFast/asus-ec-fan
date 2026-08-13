"""Single subprocess boundary for the privileged native helper."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Sequence

from .protocol import validate_percent

HELPER_API_VERSION = 2
_NO_WINDOW_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class HardwareError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class FanHardwareBackend(ABC):
    backend_name = "unknown"
    mode_readback_available = True

    @abstractmethod
    def get_status(self) -> dict[str, Any]: ...

    @abstractmethod
    def get_fan_count(self) -> int: ...

    @abstractmethod
    def get_rpm(self, fan_index: int) -> int: ...

    @abstractmethod
    def get_test_mode(self, fan_index: int) -> bool | None: ...

    @abstractmethod
    def set_percent(self, fan_index: int, percent: int) -> None: ...

    @abstractmethod
    def restore(self, fan_index: int) -> None: ...


class NativeHelperBackend(FanHardwareBackend):
    """Calls only the helper's fixed, validated command vocabulary."""

    backend_name = "Linux native EC helper"

    def __init__(
        self,
        helper_path: str | Path,
        *,
        use_sudo: bool = True,
        timeout_seconds: float = 5.0,
        validate_installation: bool = True,
    ) -> None:
        path = Path(helper_path).expanduser()
        self._path = path
        self._use_sudo = use_sudo
        self._validate_installation = validate_installation
        self._prefix: list[str] = [str(path)]
        if use_sudo:
            self._prefix = ["sudo", "-n", str(path)]
        self._timeout_seconds = timeout_seconds

    def _check_installation(self) -> None:
        if not self._validate_installation:
            return
        try:
            helper_stat = self._path.stat()
        except OSError as exc:
            raise HardwareError(
                "HELPER_UNAVAILABLE",
                "The privileged EC helper is not installed; run 'make helper', "
                "then 'sudo make install-helper'",
            ) from exc
        if not stat.S_ISREG(helper_stat.st_mode) or not os.access(self._path, os.X_OK):
            raise HardwareError(
                "HELPER_UNSAFE_INSTALLATION",
                "The configured EC helper is not an executable regular file",
            )
        if self._use_sudo and (
            helper_stat.st_uid != 0 or helper_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise HardwareError(
                "HELPER_UNSAFE_INSTALLATION",
                "The privileged EC helper must be root-owned and not writable by "
                "group or other users; run 'sudo make install-helper'",
            )

    def _run(self, arguments: Sequence[str]) -> dict[str, Any]:
        self._check_installation()
        command = [*self._prefix, *arguments]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
                creationflags=_NO_WINDOW_FLAGS,
            )
        except subprocess.TimeoutExpired as exc:
            raise HardwareError(
                "HELPER_TIMEOUT", "The privileged EC helper did not finish in time"
            ) from exc
        except OSError as exc:
            raise HardwareError("HELPER_UNAVAILABLE", str(exc)) from exc

        output = completed.stdout.strip()
        try:
            payload = json.loads(output)
        except (json.JSONDecodeError, TypeError) as exc:
            stderr = completed.stderr.strip()
            if completed.returncode != 0 and (
                "password" in stderr.lower() or "sudoers" in stderr.lower()
            ):
                raise HardwareError(
                    "PRIVILEGE_NOT_CONFIGURED",
                    "The EC helper is not authorized for passwordless sudo; "
                    "run 'sudo make install-helper'",
                ) from exc
            detail = stderr or "Helper returned invalid output"
            raise HardwareError("HELPER_INVALID_RESPONSE", detail) from exc

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            if isinstance(payload, dict):
                code = str(payload.get("error", "HELPER_FAILED"))
                message = str(payload.get("message", "EC helper request failed"))
            else:
                code, message = "HELPER_INVALID_RESPONSE", "Helper response was not an object"
            raise HardwareError(code, message)
        if completed.returncode != 0:
            raise HardwareError("HELPER_FAILED", "Helper exited unsuccessfully")
        if payload.get("helper_api") != HELPER_API_VERSION:
            raise HardwareError(
                "HELPER_VERSION_MISMATCH",
                "The installed EC helper is outdated; rebuild it and run "
                "'sudo make install-helper'",
            )
        return payload

    def get_status(self) -> dict[str, Any]:
        return self._run(["status"])

    def get_fan_count(self) -> int:
        return int(self._run(["fan-count"])["fan_count"])

    def get_rpm(self, fan_index: int) -> int:
        return int(self._run(["rpm", str(fan_index)])["rpm"])

    def get_test_mode(self, fan_index: int) -> bool:
        return bool(self._run(["test-mode", str(fan_index)])["test_mode"])

    def set_percent(self, fan_index: int, percent: int) -> None:
        value = validate_percent(percent)
        self._run(["set", str(fan_index), str(value)])

    def restore(self, fan_index: int) -> None:
        self._run(["restore", str(fan_index)])


class WindowsAsusBackend(NativeHelperBackend):
    """Calls the isolated helper that uses an official installed ASUS DLL."""

    backend_name = "ASUS System Analysis"
    mode_readback_available = False

    def __init__(self, helper_path: str | Path, *, timeout_seconds: float = 5.0) -> None:
        super().__init__(
            helper_path,
            use_sudo=False,
            timeout_seconds=timeout_seconds,
            validate_installation=False,
        )
        self._known_test_modes: dict[int, bool] = {}

    def _check_installation(self) -> None:
        if not self._path.is_file():
            raise HardwareError(
                "WINDOWS_HELPER_UNAVAILABLE",
                "The Windows ASUS helper is missing; reinstall ASUS EC Fan",
            )

    def get_test_mode(self, fan_index: int) -> bool | None:
        return self._known_test_modes.get(fan_index)

    def set_percent(self, fan_index: int, percent: int) -> None:
        value = validate_percent(percent)
        self._run(["set", str(fan_index), str(value)])
        self._known_test_modes[fan_index] = True

    def restore(self, fan_index: int) -> None:
        self._run(["restore", str(fan_index)])
        self._known_test_modes[fan_index] = False

    def get_cpu_temperature(self) -> float | None:
        value = self._run(["temperature"]).get("cpu_temperature")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        temperature = float(value)
        return round(temperature, 1) if -20.0 <= temperature <= 150.0 else None
