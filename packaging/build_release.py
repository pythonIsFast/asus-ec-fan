#!/usr/bin/env python3
"""Build one native release archive on its matching GitHub runner."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "linux-x86_64": ("Linux", {"x86_64", "amd64"}),
    "linux-arm64": ("Linux", {"aarch64", "arm64"}),
    "windows-x86_64": ("Windows", {"amd64", "x86_64"}),
    "windows-arm64": ("Windows", {"arm64", "aarch64"}),
}


def run(*arguments: str) -> None:
    subprocess.run(arguments, cwd=ROOT, check=True)


def version() -> str:
    value = os.environ.get("ASUS_EC_FAN_VERSION", "").removeprefix("v")
    value = value or (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise SystemExit("Release version must use X.Y.Z")
    return value


def verify_runner(target: str) -> None:
    expected_system, expected_machines = TARGETS[target]
    actual_system = platform.system()
    actual_machine = platform.machine().lower()
    if actual_system != expected_system or actual_machine not in expected_machines:
        raise SystemExit(
            f"Target {target} requires {expected_system} {sorted(expected_machines)}, "
            f"not {actual_system} {actual_machine}"
        )


def build(target: str) -> Path:
    release_version = version()
    verify_runner(target)
    scratch = ROOT / "build" / "release"
    app_dist = scratch / "app-dist"
    work = scratch / "pyinstaller"
    specs = scratch / "specs"
    shutil.rmtree(scratch, ignore_errors=True)
    for path in (app_dist, work, specs):
        path.mkdir(parents=True, exist_ok=True)

    separator = ";" if platform.system() == "Windows" else ":"
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "asus-ec-fan",
        "--distpath",
        str(app_dist),
        "--workpath",
        str(work / "app"),
        "--specpath",
        str(specs),
        "--add-data",
        f"{ROOT / 'frontend'}{separator}frontend",
        str(ROOT / "app.py"),
    )
    bundle = app_dist / "asus-ec-fan"

    if target.startswith("windows-"):
        helper_dist = scratch / "helper-dist"
        run(
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--name",
            "asus-ec-fan-windows-helper",
            "--distpath",
            str(helper_dist),
            "--workpath",
            str(work / "helper"),
            "--specpath",
            str(specs),
            str(ROOT / "windows_helper" / "asus_windows_helper.py"),
        )
        shutil.copy2(helper_dist / "asus-ec-fan-windows-helper.exe", bundle)
    elif target == "linux-x86_64":
        native_helper = ROOT / "helper" / "asus-ec-fan-helper"
        if not native_helper.is_file():
            raise SystemExit("Build the Linux helper before packaging")
        helper_dir = bundle / "linux-helper"
        helper_dir.mkdir()
        shutil.copy2(native_helper, helper_dir)
        shutil.copy2(ROOT / "packaging" / "asus-ec-fan.sudoers", helper_dir)

    for name in ("README.md", "LICENSE", "VERSION"):
        shutil.copy2(ROOT / name, bundle)
    shutil.copytree(ROOT / "docs", bundle / "docs")
    support = (
        "Hardware control is supported only on Linux x86-64 and Windows x86-64.\n"
        "This ARM64 package runs the GUI in mock mode; ASUS EC writes are blocked.\n"
        if target.endswith("arm64")
        else "See README.md for hardware installation and safety requirements.\n"
    )
    (bundle / "HARDWARE_SUPPORT.txt").write_text(support, encoding="utf-8")

    output = ROOT / "release"
    output.mkdir(exist_ok=True)
    basename = f"asus-ec-fan-v{release_version}-{target}"
    if target.startswith("windows-"):
        archive = output / f"{basename}.zip"
        temporary = archive.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as destination:
            for file in bundle.rglob("*"):
                if file.is_file():
                    destination.write(file, Path(basename) / file.relative_to(bundle))
    else:
        archive = output / f"{basename}.tar.gz"
        temporary = archive.with_suffix(".tar.gz.tmp")
        with tarfile.open(temporary, "w:gz", compresslevel=6) as destination:
            destination.add(bundle, arcname=basename)
    temporary.replace(archive)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    arguments = parser.parse_args()
    print(build(arguments.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
