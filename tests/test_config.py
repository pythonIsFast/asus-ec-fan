from pathlib import Path

import backend.config as config_module
from backend.config import AppConfig, is_supported_model


def test_verified_br1402fga_dmi_names_are_supported():
    assert is_supported_model("ASUS BR1402FGA")
    assert is_supported_model("BR1402FGA")
    assert is_supported_model("ASUS BR1402FGA_BR1402FGA")


def test_unknown_or_similar_models_are_not_supported():
    assert not is_supported_model("Unknown")
    assert not is_supported_model("ASUS BR1402FGA-UNVERIFIED")
    assert not is_supported_model("ASUS BR1402")


def test_linux_real_mode_uses_installed_privileged_helper(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.platform, "system", lambda: "Linux")
    config = AppConfig.defaults(tmp_path)
    assert config.helper_path.as_posix() == "/usr/local/libexec/asus-ec-fan-helper"


def test_windows_development_uses_built_narrow_helper(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(config_module.sys, "frozen", False, raising=False)
    config = AppConfig.defaults(tmp_path)
    assert config.helper_path == Path(tmp_path) / "dist" / "asus-ec-fan-windows-helper.exe"
