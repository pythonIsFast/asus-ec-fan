from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_MODELS = frozenset(
    {"ASUS BR1402FGA", "BR1402FGA", "ASUS BR1402FGA_BR1402FGA"}
)


def _read_windows_system_model() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
        ) as key:
            model, _ = winreg.QueryValueEx(key, "SystemProductName")
    except (ImportError, OSError):
        return "Unknown"
    return str(model).strip() or "Unknown"


def read_system_model(path: str | Path | None = None) -> str:
    if path is None and platform.system() == "Windows":
        return _read_windows_system_model()
    source = Path(path or "/sys/class/dmi/id/product_name")
    try:
        model = source.read_text(encoding="utf-8").strip()
    except OSError:
        return "Unknown"
    return model or "Unknown"


def is_supported_model(model: str) -> bool:
    normalized = " ".join(model.upper().split())
    return normalized in SUPPORTED_MODELS


def default_data_dir() -> Path:
    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "ASUS EC Fan"
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "asus-ec-fan"


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    database_path: Path
    helper_path: Path
    host: str = "127.0.0.1"
    port: int = 0
    mock: bool = False
    use_sudo: bool = True
    model_override: str | None = None

    @classmethod
    def defaults(cls, project_root: Path) -> "AppConfig":
        if platform.system() == "Windows":
            executable_dir = Path(sys.executable).resolve().parent
            installed_helper = executable_dir / "asus-ec-fan-windows-helper.exe"
            if not getattr(sys, "frozen", False):
                installed_helper = project_root / "dist" / "asus-ec-fan-windows-helper.exe"
        else:
            installed_helper = Path("/usr/local/libexec/asus-ec-fan-helper")
        return cls(
            project_root=project_root,
            database_path=default_data_dir() / "app.db",
            helper_path=installed_helper,
        )
