from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_MODELS = frozenset(
    {"ASUS BR1402FGA", "BR1402FGA", "ASUS BR1402FGA_BR1402FGA"}
)


def read_system_model(path: str | Path = "/sys/class/dmi/id/product_name") -> str:
    try:
        model = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return "Unknown"
    return model or "Unknown"


def is_supported_model(model: str) -> bool:
    normalized = " ".join(model.upper().split())
    return normalized in SUPPORTED_MODELS


def default_data_dir() -> Path:
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
        installed_helper = Path("/usr/local/libexec/asus-ec-fan-helper")
        return cls(
            project_root=project_root,
            database_path=default_data_dir() / "app.db",
            helper_path=installed_helper,
        )
