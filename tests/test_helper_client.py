import json
import subprocess
from types import SimpleNamespace

import pytest

from hardware.helper_client import HardwareError, NativeHelperBackend


def test_native_helper_uses_only_named_command(monkeypatch):
    observed = []

    def fake_run(command, **kwargs):
        observed.append((command, kwargs))
        return SimpleNamespace(
            stdout=json.dumps({"ok": True, "fan": 0, "mode": "manual", "percent": 60}),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = NativeHelperBackend("/safe/helper", use_sudo=True)
    backend.set_percent(0, 60)
    assert observed[0][0] == ["sudo", "-n", "/safe/helper", "set", "0", "60"]
    assert "shell" not in observed[0][1]


def test_native_helper_timeout_is_finite(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("helper", 2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = NativeHelperBackend("/safe/helper", use_sudo=False, timeout_seconds=0.01)
    with pytest.raises(HardwareError) as caught:
        backend.get_fan_count()
    assert caught.value.code == "HELPER_TIMEOUT"


def test_native_helper_preserves_structured_error(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            stdout='{"ok":false,"error":"EC_TIMEOUT_IBF","message":"busy"}',
            stderr="",
            returncode=1,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(HardwareError) as caught:
        NativeHelperBackend("/safe/helper", use_sudo=False).get_fan_count()
    assert (caught.value.code, caught.value.message) == ("EC_TIMEOUT_IBF", "busy")
