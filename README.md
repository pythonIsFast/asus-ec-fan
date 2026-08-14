<div align="center">

# ASUS EC Fan

### Safe, explicit fan control for verified ASUS laptops

A lightweight desktop application for Linux and Windows, built with Python,
Flask, SQLite, pywebview, and a framework-free frontend.

[![Build and Release](https://github.com/pythonIsFast/asus-ec-fan/actions/workflows/release.yml/badge.svg)](https://github.com/pythonIsFast/asus-ec-fan/actions/workflows/release.yml)
[![Python 3](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-2C3E50.svg)](LICENSE)
[![Frontend: Vanilla](https://img.shields.io/badge/Frontend-Vanilla_HTML%2FCSS%2FJS-2e9c69)](frontend/)

[Features](#features) · [Compatibility](#compatibility) · [Installation](#installation) · [Safety](#safety-first) · [Documentation](#documentation)

</div>

---

ASUS EC Fan displays CPU temperature, fan RPM, control mode, and live history in a clean native desktop window. It supports fixed manual duty, userspace temperature curves, persistent profiles, optional telemetry, and an always-visible **Restore firmware control** action.

The first and currently only verified laptop is the **ASUS BR1402FGA**. Unknown models are write-blocked by default.

> [!CAUTION]
> This application accesses embedded-controller fan controls. Incorrect EC access can destabilize or damage hardware. Only documented operations are implemented—there is no command scanning, raw EC API, or arbitrary port access.

> [!WARNING]
> **Windows support is currently extremely unstable** and not recommended for real use yet. Real fan control on Windows still fails on affected machines even after several fixes (console windows, ASUS DLL signature checks, and helper elevation); the Linux path is unaffected. See [Known issues](#windows-support-is-currently-unstable) below before relying on it.

> [!NOTE]
> 📷 **Screenshot placeholder:** a dashboard screenshot from verified BR1402FGA hardware will be added here.

## Features

| | Capability |
| --- | --- |
| 🌡️ | Live CPU temperature and fan RPM |
| 🎛️ | Explicit 1–100% manual fan control |
| 📈 | Graphical userspace temperature-curve editor |
| 🧩 | Firmware, fixed-duty, and curve profiles in SQLite |
| 🕒 | Optional telemetry with automatic retention cleanup |
| 🛟 | Persistent Restore action and session-owned shutdown cleanup |
| 🧪 | Hardware-safe mock mode and mocked Python/C protocol tests |
| 🔒 | Localhost-only Flask API with token-protected mutations |
| 🪶 | Vanilla HTML, CSS, and JavaScript—no frontend framework |

## Compatibility

| Platform | Architecture | Desktop / mock | Real fan control | Hardware path |
| --- | --- | :---: | :---: | --- |
| Linux | x86-64 | ✅ | ✅ BR1402FGA | Restricted native C port-I/O helper |
| Linux | ARM64 | ✅ | ❌ | Mock mode only |
| Windows | x86-64 | ✅ | ⚠️ Unstable, BR1402FGA | Official ASUS System Analysis driver |
| Windows | ARM64 | ✅ | ❌ | Mock mode only; ASUS driver is AMD64 |

Real writes require an exact model match. Verified DMI names are:

```text
ASUS BR1402FGA
BR1402FGA
ASUS BR1402FGA_BR1402FGA
```

Adding another model requires documented hardware verification. Similar model names are not considered compatible automatically.

## Architecture

```text
pywebview desktop window
        │
        ▼
Vanilla HTML / CSS / JavaScript
        │ fetch()
        ▼
Flask on 127.0.0.1
        │
        ▼
FanService / profiles / curves / SQLite
        │
        ├── Linux  → restricted native C helper → verified EC ports
        └── Windows → restricted Python helper → ASUS System Analysis DLL
```

The Flask and pywebview process runs without root or Windows administrator privileges. Hardware access is isolated behind one narrow helper boundary per platform.

## Installation

### Linux

Requirements:

- Python 3.10 or newer with `venv`
- GCC or Clang and development headers
- Qt runtime libraries for PySide6/pywebview
- `sudo` for the installed native helper
- verified ASUS BR1402FGA for real writes

On Debian or Ubuntu, begin with:

```sh
sudo apt install python3-venv build-essential
```

Set up the project and run the hardware-safe tests:

```sh
make setup
make
make test
```

Install the privileged helper as your normal user, elevating only the installation steps:

```sh
make helper
sudo make install-helper
sudo make authorize-user
```

If `sudo` does not preserve `SUDO_USER`, specify the desktop account:

```sh
sudo make authorize-user TARGET_USER=marian
```

Log out and back in after group membership changes. The installed helper is root-owned, non-setuid, restricted by a validated sudoers rule, and independently blocks unknown DMI models.

### Windows

Use the packaged `asus-ec-fan.exe`. Real control requires Windows x86-64 and the official ASUS software stack:

- ASUS System Control Interface
- ASUS System Analysis service
- the ASUS-signed `AsusWinIO64.dll`

The project does **not** bundle or download this proprietary DLL. The helper searches only the expected `asussci2.inf_amd64_*` DriverStore location and rejects a DLL without a valid ASUSTeK Authenticode signature.

> [!IMPORTANT]
> Project release executables are currently unsigned, so Windows SmartScreen may show an unknown-publisher warning. This is separate from the mandatory signature verification of ASUS's installed driver DLL.

## Running the application

| Mode | Command |
| --- | --- |
| Normal Linux desktop | `make run` |
| Safe simulated hardware | `make mock` |
| Browser development | `.venv/bin/python app.py --mock --no-gui` |
| Windows development | `python app.py --mock` |

Flask selects an unused port and binds only to `127.0.0.1`. Moving the fan slider never changes hardware by itself; the user must select **Apply manual speed**.

## Safety first

### Manual control

On Linux, Apply uses only the verified sequence: wake, ASUS fan command, select fan, enable test mode, and set PWM. Percentages are validated in Python and C. Success is shown only after Linux reads test mode back from the EC.

The known Windows DLL has a test-mode setter but no known getter. Windows therefore starts in **Unknown** mode and blocks Apply. Select **Restore firmware control** once to establish a known firmware baseline before enabling session-owned manual control.

### Restore and shutdown

Restore selects the fan, disables ASUS test mode, and sends the known-good PWM-0 completion. If this application moved a fan from firmware into manual mode, it attempts to restore firmware control during:

- SIGINT or SIGTERM
- pywebview window close
- normal Python shutdown

The application does not automatically overwrite a manual state it did not establish. A hard crash, power loss, or kernel failure can prevent cleanup; use Restore and reboot if firmware ownership is uncertain.

### Curves and profiles

Curves contain 2–8 monotonic points between 20–100 °C and 1–100% duty. They are an explicitly started userspace loop—not an undocumented EC curve command. Missing temperature data or hardware errors stop the controller. Saved profiles are never applied automatically at startup.

## Data and telemetry

SQLite stores settings, profiles, events, and optional telemetry. It is never treated as the source of truth for live hardware state.

| Platform | Default database |
| --- | --- |
| Linux | `${XDG_DATA_HOME}/asus-ec-fan/app.db` or `~/.local/share/asus-ec-fan/app.db` |
| Windows | `%LOCALAPPDATA%\ASUS EC Fan\app.db` |

Telemetry is disabled by default. When enabled, samples are rate-limited and data older than the configured retention period is deleted automatically.

## Troubleshooting

### Windows support is currently unstable

Real fan control on Windows has repeatedly failed on affected hardware even after several targeted fixes: a `pywebview`/pythonnet DLL-load error, a false-negative ASUS driver signature check, and the helper needing Administrator rights it never requested. The current state:

- The helper now elevates itself once via a UAC prompt and talks to the ASUS driver over a named pipe for the rest of the session (see [`docs/security.md`](docs/security.md)).
- Despite that, `fan-count`/EC access has continued to fail on at least one real device after each fix so far, with no further diagnostic output yet available from that hardware.
- Linux fan control is unaffected by any of this.

If you hit a Windows error, please open an issue with the exact error text and the app version — the messages are intentionally specific (they include the actual driver response, signature subject, etc.) to make root-causing this remotely possible.

<details>
<summary><strong>Unsupported hardware</strong></summary>

Only verified BR1402FGA identifiers can perform writes. Use `--mock` for UI development on other hardware.

</details>

<details>
<summary><strong>Linux helper unavailable or privilege not configured</strong></summary>

Run the helper installation again, log out and back in, then verify it:

```sh
make helper
sudo make install-helper
sudo make authorize-user
sudo -n /usr/local/libexec/asus-ec-fan-helper status
```

</details>

<details>
<summary><strong>GTK or Qt cannot be loaded</strong></summary>

Run `make setup` again and install any shared library named in the Qt error. Use `--no-gui` as a browser fallback.

</details>

<details>
<summary><strong>Windows: "Failed to resolve Python.Runtime.Loader.Initialize"</strong></summary>

Windows marks files extracted from a downloaded ZIP as coming from the internet (Mark of the Web). .NET Framework then refuses to load the bundled `Python.Runtime.dll`, which pywebview's desktop window needs. The app clears this mark from its own bundle on startup; if the error still appears (e.g. antivirus reapplied it, or the folder is read-only), right-click the ZIP before extracting → Properties → check **Unblock** → OK, then re-extract, or run `Unblock-File -Path .\asus-ec-fan-*.zip` in PowerShell first.

</details>

<details>
<summary><strong>Windows driver missing, untrusted, or mode Unknown</strong></summary>

Install or repair MyASUS, ASUS System Control Interface, and ASUS System Analysis. Unsigned replacement DLLs are rejected. If mode is **Unknown**, select Restore once before Apply.

</details>

<details>
<summary><strong>No CPU temperature, failed verification, or EC timeout</strong></summary>

On Linux, inspect `/sys/class/hwmon` and `/sys/class/thermal`. For write or timeout errors, stop making changes, attempt Restore if safe, and reboot. Never retry by scanning commands or registers.

</details>

Explicit read-only hardware checks are available through:

```sh
sudo make hardware-test
```

## Development

```sh
make setup   # create/update the virtual environment
make helper  # build only the Linux C helper
make test    # hardware-safe Python and simulated C tests
make mock    # run the desktop UI without hardware access
```

Normal tests never execute `ioperm`, `inb`, `outb`, `/dev/port`, the production Linux helper, or the ASUS Windows driver. Hardware tests require explicit execution.

## Releases

The **Build and Release** GitHub Action runs on every push and produces native artifacts for:

- Linux x86-64
- Linux ARM64
- Windows x86-64
- Windows ARM64

To publish a release, bump `VERSION` and push to `main` — no tag needs to be created or pushed by hand:

```sh
echo 0.2.0 > VERSION
git commit -am "Bump version to 0.2.0"
git push origin main
```

The workflow creates the `vX.Y.Z` tag and the GitHub Release itself once every test and platform build succeeds, and skips publishing again if that version was already released.

## Documentation

- [Verified EC protocol](docs/protocol.md)
- [Application architecture](docs/architecture.md)
- [Security model](docs/security.md)
- [Agent contribution rules](AGENTS.md)

Read the protocol and security documents before changing hardware code. Preserve finite timeouts, helper isolation, input validation, and session-owned restore behavior.

## License

Licensed under the [GNU General Public License v3.0](LICENSE).
