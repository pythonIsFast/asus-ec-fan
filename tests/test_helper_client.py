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
            stdout=json.dumps(
                {
                    "ok": True,
                    "helper_api": 2,
                    "fan": 0,
                    "mode": "manual",
                    "percent": 60,
                }
            ),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = NativeHelperBackend(
        "/safe/helper", use_sudo=True, validate_installation=False
    )
    backend.set_percent(0, 60)
    assert observed[0][0] == ["sudo", "-n", "/safe/helper", "set", "0", "60"]
    assert "shell" not in observed[0][1]


def test_native_helper_timeout_is_finite(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("helper", 2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = NativeHelperBackend(
        "/safe/helper",
        use_sudo=False,
        timeout_seconds=0.01,
        validate_installation=False,
    )
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
        NativeHelperBackend(
            "/safe/helper", use_sudo=False, validate_installation=False
        ).get_fan_count()
    assert (caught.value.code, caught.value.message) == ("EC_TIMEOUT_IBF", "busy")


def test_native_helper_explains_missing_sudo_policy(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            stdout="",
            stderr="sudo: a password is required",
            returncode=1,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(HardwareError) as caught:
        NativeHelperBackend(
            "/safe/helper", use_sudo=True, validate_installation=False
        ).get_status()
    assert caught.value.code == "PRIVILEGE_NOT_CONFIGURED"
    assert "install-helper" in caught.value.message


def test_native_helper_rejects_outdated_installed_binary(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            stdout='{"ok":true,"status":0,"obf":false,"ibf":false}',
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(HardwareError) as caught:
        NativeHelperBackend(
            "/safe/helper", use_sudo=False, validate_installation=False
        ).get_status()
    assert caught.value.code == "HELPER_VERSION_MISMATCH"


def test_native_helper_reports_missing_installation(tmp_path):
    backend = NativeHelperBackend(tmp_path / "missing-helper", use_sudo=True)
    with pytest.raises(HardwareError) as caught:
        backend.get_status()
    assert caught.value.code == "HELPER_UNAVAILABLE"


def test_native_helper_rejects_user_owned_privileged_binary(tmp_path):
    helper = tmp_path / "helper"
    helper.write_text("not executed", encoding="utf-8")
    helper.chmod(0o755)
    backend = NativeHelperBackend(helper, use_sudo=True)
    with pytest.raises(HardwareError) as caught:
        backend.get_status()
    assert caught.value.code == "HELPER_UNSAFE_INSTALLATION"
