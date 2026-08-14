import json

import pytest

from backend.fan_service import FanService, FanServiceError
from hardware.helper_client import HardwareError, WindowsAsusBackend


class FakePipe:
    """Stands in for a connected named pipe, driven by a plain responder."""

    def __init__(self, responder):
        self._responder = responder
        self._pending = b""

    def write(self, data: bytes) -> None:
        arguments = json.loads(data.decode("utf-8").rstrip("\n"))
        payload = self._responder(arguments)
        self._pending = (json.dumps(payload) + "\n").encode("utf-8")

    def read(self, max_bytes: int) -> bytes:
        chunk, self._pending = self._pending[:max_bytes], self._pending[max_bytes:]
        return chunk

    def close(self) -> None:
        pass


def make_backend(tmp_path, responder):
    helper = tmp_path / "asus-ec-fan-windows-helper.exe"
    helper.write_bytes(b"helper")

    def fake_connect(_pipe_name, *, timeout_seconds):
        return FakePipe(responder)

    def fake_elevate(_helper_path, _pipe_name):
        raise AssertionError("elevate() should not run when the pipe is already connectable")

    return WindowsAsusBackend(helper, connect=fake_connect, elevate=fake_elevate)


def test_windows_backend_requires_explicit_restore_baseline(tmp_path):
    calls = []

    def responder(arguments):
        calls.append(arguments)
        payload = {"ok": True, "helper_api": 2}
        if arguments[0] == "fan-count":
            payload["fan_count"] = 1
        return payload

    backend = make_backend(tmp_path, responder)
    service = FanService(backend, model="ASUS BR1402FGA", writes_allowed=True)

    with pytest.raises(FanServiceError) as error:
        service.set_manual(0, 60)
    assert error.value.code == "MODE_BASELINE_REQUIRED"
    assert ["set", "0", "60"] not in calls

    service.restore(0)
    result = service.set_manual(0, 60)
    assert result["mode"] == "manual"
    assert result["verified"] is False
    assert calls[-2:] == [["fan-count"], ["set", "0", "60"]]


def test_windows_backend_tracks_only_successful_session_state(tmp_path):
    def responder(arguments):
        payload = {"ok": True, "helper_api": 2}
        if arguments[0] == "fan-count":
            payload["fan_count"] = 1
        return payload

    backend = make_backend(tmp_path, responder)
    assert backend.get_test_mode(0) is None
    backend.restore(0)
    assert backend.get_test_mode(0) is False
    backend.set_percent(0, 80)
    assert backend.get_test_mode(0) is True


def test_windows_backend_elevates_when_pipe_is_not_yet_running(tmp_path):
    import hardware.windows_pipe as windows_pipe

    helper = tmp_path / "asus-ec-fan-windows-helper.exe"
    helper.write_bytes(b"helper")
    attempts = []

    def responder(arguments):
        payload = {"ok": True, "helper_api": 2}
        if arguments[0] == "fan-count":
            payload["fan_count"] = 1
        return payload

    def fake_connect(_pipe_name, *, timeout_seconds):
        attempts.append(timeout_seconds)
        if len(attempts) == 1:
            raise windows_pipe.PipeError("not running yet")
        return FakePipe(responder)

    elevated = []

    def fake_elevate(helper_path, pipe_name):
        elevated.append((helper_path, pipe_name))

    backend = WindowsAsusBackend(helper, connect=fake_connect, elevate=fake_elevate)
    assert backend.get_fan_count() == 1
    assert elevated == [(helper, windows_pipe.PIPE_NAME)]
    assert len(attempts) == 2


def test_windows_backend_reports_declined_elevation(tmp_path):
    import hardware.windows_pipe as windows_pipe

    helper = tmp_path / "asus-ec-fan-windows-helper.exe"
    helper.write_bytes(b"helper")

    def fake_connect(_pipe_name, *, timeout_seconds):
        raise windows_pipe.PipeError("not running yet")

    def fake_elevate(_helper_path, _pipe_name):
        raise windows_pipe.ElevationDeclined("Administrator approval was not granted")

    backend = WindowsAsusBackend(helper, connect=fake_connect, elevate=fake_elevate)
    with pytest.raises(HardwareError) as error:
        backend.get_fan_count()
    assert error.value.code == "HELPER_ELEVATION_DECLINED"
