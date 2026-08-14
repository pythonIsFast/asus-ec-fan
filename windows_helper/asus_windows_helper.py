"""Narrow Windows bridge to the officially installed ASUS System Analysis DLL.

The ASUS DLL is proprietary and is deliberately neither bundled nor downloaded.
This executable accepts only the fixed fan operations used by the application.
"""

from __future__ import annotations

import base64
import ctypes
import glob
import json
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

HELPER_API_VERSION = 2
MAX_FANS = 8
MUTEX_TIMEOUT_MS = 5_000
_NO_WINDOW_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class HelperError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def percent_to_pwm(percent: object) -> int:
    if isinstance(percent, bool):
        raise HelperError("INVALID_PERCENT", "Percent must be an integer from 1 to 100")
    try:
        value = int(percent)
    except (TypeError, ValueError) as exc:
        raise HelperError("INVALID_PERCENT", "Percent must be an integer from 1 to 100") from exc
    if str(value) != str(percent).strip() or not 1 <= value <= 100:
        raise HelperError("INVALID_PERCENT", "Percent must be an integer from 1 to 100")
    return (value * 255 + 50) // 100


def ensure_supported_platform() -> None:
    if platform.system() != "Windows":
        raise HelperError("UNSUPPORTED_PLATFORM", "The ASUS Windows helper only runs on Windows")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise HelperError(
            "UNSUPPORTED_ARCHITECTURE",
            "ASUS EC hardware control requires Windows x86-64; this build supports mock mode only",
        )


def find_asus_dll() -> Path:
    windows_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    repository = windows_root / "System32" / "DriverStore" / "FileRepository"
    pattern = str(repository / "asussci2.inf_amd64_*" / "ASUSSystemAnalysis" / "AsusWinIO64.dll")
    candidates = [Path(item) for item in glob.glob(pattern)]
    if not candidates:
        raise HelperError(
            "ASUS_DRIVER_NOT_FOUND",
            "Install MyASUS, ASUS System Control Interface, and ASUS System Analysis",
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def verify_asus_signature(path: Path) -> None:
    # The path is embedded as base64 rather than passed as a trailing argument
    # so quoting/$args binding can't misdirect -Command, and -ExecutionPolicy
    # Bypass keeps a machine-wide Restricted/AllSigned policy from silently
    # blocking this single invocation.
    encoded_path = base64.b64encode(str(path).encode("utf-16-le")).decode("ascii")
    script = (
        f"$p=[System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded_path}'));"
        "$s=Get-AuthenticodeSignature -LiteralPath $p;"
        "[pscustomobject]@{Status=$s.Status.ToString();"
        "Subject=$s.SignerCertificate.Subject}|ConvertTo-Json -Compress"
    )
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=_NO_WINDOW_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HelperError(
            "ASUS_DLL_UNTRUSTED", f"Could not run powershell.exe to verify the ASUS DLL signature: {exc}"
        ) from exc
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = result.stderr.strip() or result.stdout.strip() or str(exc)
        raise HelperError(
            "ASUS_DLL_UNTRUSTED", f"Could not verify the ASUS DLL signature: {detail}"
        ) from exc
    subject = str(payload.get("Subject", ""))
    subject_upper = subject.upper()
    # Windows driver-signing enforcement means a DLL can only reach the
    # DriverStore path we glob for (find_asus_dll) via a signed driver
    # install. Modern drivers are commonly submitted through Microsoft's
    # WHQL/attestation program, which re-signs them with a Microsoft
    # certificate instead of the vendor's, so accept that publisher too.
    recognized_signers = ("ASUSTEK", "MICROSOFT WINDOWS HARDWARE COMPATIBILITY PUBLISHER")
    if (
        result.returncode != 0
        or payload.get("Status") != "Valid"
        or not any(signer in subject_upper for signer in recognized_signers)
    ):
        raise HelperError(
            "ASUS_DLL_UNTRUSTED",
            "The installed ASUS DLL has no valid ASUS signature "
            f"(status={payload.get('Status')!r}, subject={subject!r})",
        )


class AsusDll:
    def __init__(self, path: Path) -> None:
        try:
            self._dll = ctypes.WinDLL(str(path))
        except (OSError, AttributeError) as exc:
            raise HelperError("ASUS_DLL_LOAD_FAILED", "Could not load the ASUS System Analysis DLL") from exc
        self._bind()

    def _function(self, name: str, argtypes: list[Any], restype: Any) -> Any:
        try:
            function = getattr(self._dll, name)
        except AttributeError as exc:
            raise HelperError("ASUS_DLL_INCOMPATIBLE", f"Required ASUS export is missing: {name}") from exc
        function.argtypes = argtypes
        function.restype = restype
        return function

    def _bind(self) -> None:
        self.initialize = self._function("InitializeWinIo", [], None)
        self.shutdown = self._function("ShutdownWinIo", [], None)
        self.fan_count = self._function("HealthyTable_FanCounts", [], ctypes.c_int)
        self.select_fan = self._function("HealthyTable_SetFanIndex", [ctypes.c_ubyte], None)
        self.read_rpm = self._function("HealthyTable_FanRPM", [], ctypes.c_int)
        self.set_test_mode = self._function(
            "HealthyTable_SetFanTestMode", [ctypes.c_uint16], None
        )
        self.set_pwm = self._function("HealthyTable_SetFanPwmDuty", [ctypes.c_short], None)
        self.read_temperature = self._function("Thermal_Read_Cpu_Temperature", [], ctypes.c_uint64)


@contextmanager
def helper_mutex() -> Iterator[None]:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Local\\AsusEcFan.Windows.Helper")
    if not handle:
        raise HelperError("LOCK_FAILED", "Could not create the ASUS helper lock")
    try:
        result = kernel32.WaitForSingleObject(handle, MUTEX_TIMEOUT_MS)
        if result not in (0x00000000, 0x00000080):
            raise HelperError("HELPER_BUSY", "Timed out waiting for another ASUS helper operation")
        try:
            yield
        finally:
            kernel32.ReleaseMutex(handle)
    finally:
        kernel32.CloseHandle(handle)


def parse_fan(value: str, count: int) -> int:
    try:
        fan = int(value)
    except ValueError as exc:
        raise HelperError("INVALID_FAN", "Fan index must be an integer") from exc
    if str(fan) != value.strip() or not 0 <= fan < count:
        raise HelperError("INVALID_FAN", f"Fan index must be between 0 and {count - 1}")
    return fan


def execute(arguments: Sequence[str], dll: Any) -> dict[str, Any]:
    command = arguments[0] if arguments else ""
    allowed_counts = {"status": 1, "fan-count": 1, "temperature": 1, "rpm": 2, "set": 3, "restore": 2}
    if command not in allowed_counts or len(arguments) != allowed_counts.get(command):
        raise HelperError("INVALID_COMMAND", "Unsupported helper command or argument count")

    count = int(dll.fan_count())
    if not 1 <= count <= MAX_FANS:
        raise HelperError(
            "INVALID_FAN_COUNT",
            f"ASUS driver returned an invalid fan count ({count}); it may need "
            "Administrator privileges to access the EC, or MyASUS/ASUS System "
            "Control Interface may need a repair install",
        )
    base: dict[str, Any] = {"ok": True, "helper_api": HELPER_API_VERSION}
    if command == "status":
        return {**base, "status": None, "source": "asus-driver", "dll_verified": True}
    if command == "fan-count":
        return {**base, "fan_count": count}
    if command == "temperature":
        temperature = int(dll.read_temperature())
        if not -20 <= temperature <= 150:
            raise HelperError("INVALID_TEMPERATURE", "ASUS driver returned an invalid temperature")
        return {**base, "cpu_temperature": temperature}

    fan = parse_fan(arguments[1], count)
    dll.select_fan(fan)
    if command == "rpm":
        rpm = int(dll.read_rpm())
        if not 0 <= rpm <= 100_000:
            raise HelperError("INVALID_RPM", "ASUS driver returned an invalid fan speed")
        return {**base, "fan": fan, "rpm": rpm}
    if command == "set":
        pwm = percent_to_pwm(arguments[2])
        percent = int(arguments[2])
        dll.set_test_mode(1)
        dll.set_pwm(pwm)
        return {**base, "fan": fan, "mode": "manual", "percent": percent, "pwm": pwm}

    # Preserve the previously verified restore sequence: disable test mode, then PWM 0.
    dll.set_test_mode(0)
    dll.set_pwm(0)
    return {**base, "fan": fan, "mode": "firmware"}


def run(
    arguments: Sequence[str],
    *,
    dll_factory: Callable[[Path], Any] = AsusDll,
    lock_factory: Callable[[], Any] = helper_mutex,
) -> dict[str, Any]:
    ensure_supported_platform()
    dll_path = find_asus_dll()
    verify_asus_signature(dll_path)
    with lock_factory():
        dll = dll_factory(dll_path)
        dll.initialize()
        try:
            return execute(arguments, dll)
        finally:
            dll.shutdown()


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        payload = run(list(arguments if arguments is not None else sys.argv[1:]))
        exit_code = 0
    except HelperError as exc:
        payload = {"ok": False, "error": exc.code, "message": exc.message}
        exit_code = 1
    except Exception:
        payload = {"ok": False, "error": "HELPER_FAILED", "message": "ASUS helper failed safely"}
        exit_code = 1
    print(json.dumps(payload, separators=(",", ":")), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
