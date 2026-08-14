"""Named-pipe transport used to talk to the elevated Windows ASUS helper.

The GUI/Flask process must stay unprivileged (see docs/security.md), so the
ASUS helper is instead started once, elevated via a UAC prompt, as a
long-lived named-pipe server (see windows_helper/asus_windows_helper.py's
``serve_forever``). Every later command reuses that same connection, so only
the first hardware access of a session prompts for Administrator approval.

All ctypes/Win32 access is confined to functions (never module import time)
so this module can still be imported on non-Windows platforms for tests.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import time
from pathlib import Path
from typing import Any, Protocol, Sequence

PIPE_NAME = r"\\.\pipe\AsusEcFan.Helper"
SHUTDOWN_COMMAND = "__shutdown__"

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PIPE_BUSY = 231
_SW_HIDE = 0
_INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


class PipeError(RuntimeError):
    """Transport failure talking to the elevated ASUS helper."""


class ElevationDeclined(PipeError):
    """The UAC prompt to elevate the helper was declined or blocked."""


class Pipe(Protocol):
    def write(self, data: bytes) -> None: ...
    def read(self, max_bytes: int) -> bytes: ...
    def close(self) -> None: ...


class Win32Pipe:
    """Wraps a connected pipe HANDLE with a minimal read/write/close surface."""

    def __init__(self, handle: int) -> None:
        self._handle = handle
        self._kernel32 = _kernel32()

    def write(self, data: bytes) -> None:
        written = wintypes.DWORD(0)
        ok = self._kernel32.WriteFile(self._handle, data, len(data), ctypes.byref(written), None)
        if not ok:
            raise PipeError(
                f"Could not send the request to the ASUS helper (error {self._kernel32.GetLastError()})"
            )

    def read(self, max_bytes: int) -> bytes:
        buffer = ctypes.create_string_buffer(max_bytes)
        read = wintypes.DWORD(0)
        ok = self._kernel32.ReadFile(self._handle, buffer, max_bytes, ctypes.byref(read), None)
        if not ok:
            return b""
        return buffer.raw[: read.value]

    def close(self) -> None:
        self._kernel32.CloseHandle(self._handle)


def _kernel32():
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPDWORD,
        wintypes.LPVOID,
    ]
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPDWORD,
        wintypes.LPVOID,
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.GetLastError.restype = wintypes.DWORD
    return kernel32


def _shell32():
    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    shell32.ShellExecuteW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    return shell32


def connect(pipe_name: str, *, timeout_seconds: float) -> Pipe:
    """Open an already-running helper's pipe, waiting for it to become ready."""
    kernel32 = _kernel32()
    deadline = time.monotonic() + timeout_seconds
    while True:
        handle = kernel32.CreateFileW(
            pipe_name, _GENERIC_READ | _GENERIC_WRITE, 0, None, _OPEN_EXISTING, 0, None
        )
        if handle not in (0, _INVALID_HANDLE_VALUE):
            return Win32Pipe(handle)
        error = kernel32.GetLastError()
        if error not in (_ERROR_FILE_NOT_FOUND, _ERROR_PIPE_BUSY):
            raise PipeError(f"Could not open the ASUS helper pipe (error {error})")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PipeError("Timed out waiting for the ASUS helper to start")
        kernel32.WaitNamedPipeW(pipe_name, max(1, int(remaining * 1000)))


def elevate(helper_path: Path, pipe_name: str) -> None:
    """Launch the helper elevated via UAC; raises if approval is refused."""
    shell32 = _shell32()
    result = shell32.ShellExecuteW(
        None, "runas", str(helper_path), f'--serve "{pipe_name}"', None, _SW_HIDE
    )
    code = int(result or 0)
    if code <= 32:
        raise ElevationDeclined(f"Administrator approval was not granted (code {code})")


def send_request(pipe: Pipe, arguments: Sequence[str], *, timeout_seconds: float) -> dict[str, Any]:
    """Send one newline-delimited JSON request and read the matching response."""
    message = (json.dumps(list(arguments)) + "\n").encode("utf-8")
    pipe.write(message)

    buffer = bytearray()
    deadline = time.monotonic() + timeout_seconds
    while b"\n" not in buffer:
        if time.monotonic() > deadline:
            raise PipeError("Timed out waiting for the ASUS helper's response")
        chunk = pipe.read(4096)
        if not chunk:
            raise PipeError("The ASUS helper closed the connection unexpectedly")
        buffer.extend(chunk)

    line = buffer.split(b"\n", 1)[0]
    try:
        payload = json.loads(line.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PipeError(f"The ASUS helper returned malformed output: {line!r}") from exc
    if not isinstance(payload, dict):
        raise PipeError(f"The ASUS helper returned malformed output: {line!r}")
    return payload
