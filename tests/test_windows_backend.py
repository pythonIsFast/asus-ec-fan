import json

import pytest

from backend.fan_service import FanService, FanServiceError
from hardware.helper_client import WindowsAsusBackend


def test_windows_backend_requires_explicit_restore_baseline(tmp_path, monkeypatch):
    helper = tmp_path / "asus-ec-fan-windows-helper.exe"
    helper.write_bytes(b"helper")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command[1:])
        action = command[1]
        payload = {"ok": True, "helper_api": 2}
        if action == "fan-count":
            payload["fan_count"] = 1
        return type("Result", (), {"stdout": json.dumps(payload), "stderr": "", "returncode": 0})()

    monkeypatch.setattr("hardware.helper_client.subprocess.run", fake_run)
    backend = WindowsAsusBackend(helper)
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


def test_windows_backend_tracks_only_successful_session_state(tmp_path, monkeypatch):
    helper = tmp_path / "asus-ec-fan-windows-helper.exe"
    helper.write_bytes(b"helper")

    def fake_run(command, **_kwargs):
        payload = {"ok": True, "helper_api": 2}
        if command[1] == "fan-count":
            payload["fan_count"] = 1
        return type("Result", (), {"stdout": json.dumps(payload), "stderr": "", "returncode": 0})()

    monkeypatch.setattr("hardware.helper_client.subprocess.run", fake_run)
    backend = WindowsAsusBackend(helper)
    assert backend.get_test_mode(0) is None
    backend.restore(0)
    assert backend.get_test_mode(0) is False
    backend.set_percent(0, 80)
    assert backend.get_test_mode(0) is True
