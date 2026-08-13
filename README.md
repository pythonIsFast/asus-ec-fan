# ASUS EC Fan

ASUS EC Fan is a small Linux and Windows desktop application for reading and explicitly controlling the CPU fan on verified ASUS laptops. The first supported system is the **ASUS BR1402FGA**.

> **Warning:** This application accesses embedded-controller hardware. Incorrect EC access can destabilize or damage a machine. Only the documented BR1402FGA protocol is implemented. Unknown models are write-blocked by default.

The light, desktop-oriented dashboard shows the detected model, CPU temperature, current RPM, live session history, and whether ASUS fan test/manual mode is active. Dedicated views expose fixed fan control, userspace temperature curves, live sensors, persistent profiles, settings, and compatibility details. A slider prepares a percentage, but no hardware change occurs until **Apply manual speed** is selected. **Restore firmware control** remains available from every view and disables ASUS test mode.

## Capabilities

- Linux and Windows, Python 3, Flask, SQLite, pywebview
- framework-free HTML, CSS, and JavaScript
- minimal native C helper for ports `0x25c` and `0x25d`
- isolated Windows helper for the officially installed ASUS System Analysis driver
- one verified model: ASUS BR1402FGA
- safe mock mode and mocked Python/C protocol tests
- localhost-only, token-protected mutation API
- optional telemetry with retention cleanup
- SQLite-backed firmware, fixed-duty, and temperature-curve profiles
- explicit userspace curve controller with bounded, validated points
- verified manual/restore transitions before success is shown

Screenshot placeholder: capture the application on verified BR1402FGA hardware after installation.

## Linux requirements

- Linux on x86 with GCC or Clang and development headers
- Python 3.10 or newer with `venv`
- Qt system libraries required by the PySide6/pywebview runtime
- `sudo` configured for the installed helper
- verified ASUS BR1402FGA for real writes

The Python setup installs pywebview together with its PySide6 Qt backend inside the virtual environment. On Debian/Ubuntu, the basic build packages are `python3-venv` and `build-essential`. A minimal desktop installation may additionally need system libraries used by Qt; package names vary by distribution.

## Windows requirements

Real control requires Windows x86-64, a supported BR1402FGA, and the official ASUS software stack: ASUS System Control Interface, ASUS System Analysis, and its ASUS-signed `AsusWinIO64.dll`. The application does not ship or download this proprietary DLL. It searches only the expected `asussci2.inf_amd64_*` DriverStore location and rejects a DLL without a valid ASUSTeK Authenticode signature.

Windows ARM64 builds run the UI and mock mode natively, but the current ASUS AMD64 driver cannot provide ARM64 hardware access.

Project release executables are currently unsigned, so Windows SmartScreen may show an unknown-publisher warning. That is separate from the mandatory signature check on ASUS's installed driver DLL.

## Build and test

```sh
make setup
make
make test
```

Run `make setup` again after dependency changes. It updates an existing virtual environment as well as creating a new one.

`make test` is hardware-safe. Python tests use the mock backend, while C protocol tests replace `ioperm`, `inb`, and `outb` with a simulated I/O backend and assert the exact `FF → DD → payload` ordering. The production helper is never executed by the normal test target.

To build only the native helper:

```sh
make helper
```

## Install privileged helper

Build as your normal user, then use the validated installation targets:

```sh
make helper
sudo make install-helper
sudo make authorize-user
```

`install-helper` validates the packaged sudoers policy, creates the dedicated `asus-ec-fan` system group, and installs a root-owned, non-setuid binary. `authorize-user` adds the invoking desktop user to that group. If `sudo` does not preserve `SUDO_USER`, specify it explicitly:

```sh
sudo make authorize-user TARGET_USER=marian
```

Log out and back in after changing group membership. The helper itself accepts only its fixed command vocabulary and independently blocks writes on unknown DMI models. Review [the security model](docs/security.md) before installation.

Repeat `make helper` and `sudo make install-helper` after native-helper updates. The Python client checks the helper API version and rejects an outdated installed binary instead of sending commands through an incompatible implementation.

## Run

Normal desktop window:

```sh
make run
```

Safe simulated hardware:

```sh
make mock
```

Browser development mode:

```sh
.venv/bin/python app.py --mock --no-gui
```

On Windows, use the packaged `asus-ec-fan.exe`. For safe development from a checkout, run `python app.py --mock`; this makes no driver calls or fan writes.

The service selects an unused localhost port by default. It never binds to an external interface and the GUI refuses to start as root. Real mode uses only the installed helper path by default and rejects a privileged helper that is not root-owned or is writable by group/other users.

## Manual and restore behavior

On Linux, Apply performs the working sequence: `0xff` wake, `0xdd` command, select fan, enable ASUS test mode, then set PWM. The percentage range is 1–100 and conversion is validated in both Python and C. The Linux helper reads test mode back and reports success only after the EC confirms manual mode.

The ASUS Windows DLL offers a test-mode setter but no known getter. Windows therefore starts in **Unknown** mode and blocks Apply. Click **Restore firmware control** once to establish a known firmware baseline for this process; only then can Apply enable a session-owned manual mode.

Restore selects the fan, disables ASUS test mode, sends the known-good PWM-0 completion, and verifies firmware mode. If this application moved a fan from firmware into manual mode, a clean SIGINT, SIGTERM, window close, or normal shutdown attempts the same restore. It does not automatically restore a test mode that was already active before this session.

A crash or power loss can prevent cleanup. Always keep the Restore action accessible, and reboot if firmware ownership is uncertain.

## Curves and profiles

The Curves page supports 2–8 points between 20–100 °C and 1–100% duty. Temperatures must increase and duty may not decrease. This does **not** send an undocumented fan-curve packet to the EC: it is an explicitly started userspace loop that reads the normal Linux CPU sensor, interpolates a percentage, and uses only the verified fixed-duty operation. It stops if temperature data or hardware access fails. If it established ASUS test mode, **Stop & restore** and clean application shutdown return control to firmware.

Profiles are stored in SQLite and are never applied automatically at startup. Built-in examples cover firmware control, fixed 60%, and a temperature curve. Users can create firmware, fixed-duty, or current-curve profiles, explicitly apply them, and delete inactive custom profiles. Direct manual or Restore actions first stop a running curve so it cannot overwrite the new command.

## Settings and telemetry

SQLite data defaults to `${XDG_DATA_HOME}/asus-ec-fan/app.db` or `~/.local/share/asus-ec-fan/app.db` on Linux, and `%LOCALAPPDATA%\ASUS EC Fan\app.db` on Windows. Settings include polling interval, telemetry toggle and retention, selected fan, and window dimensions.

Telemetry is disabled by default. When enabled it records at most one sample per fan every 10 seconds (or the longer configured poll interval) and removes data older than the retention period.

## Troubleshooting

- **Unsupported hardware:** verified DMI names are `ASUS BR1402FGA`, `BR1402FGA`, and the observed firmware form `ASUS BR1402FGA_BR1402FGA`. Unknown systems remain read-only. Use `--mock` for UI development.
- **Helper unavailable / privilege not configured:** run `make helper`, `sudo make install-helper`, and `sudo make authorize-user`, then log out and back in. Verify with `sudo -n /usr/local/libexec/asus-ec-fan-helper status`.
- **Apply fails verification:** the application intentionally refuses to claim success if test mode does not read back as enabled. Restore firmware control, stop the application, and inspect the displayed structured error before trying again.
- **Permission denied:** `ioperm()` requires root/CAP_SYS_RAWIO. Do not run the GUI as root and do not make the helper setuid.
- **`GTK cannot be loaded` / `QT cannot be loaded`:** run `make setup` again. The project now installs and explicitly selects the PySide6 Qt backend. If Qt still reports a missing shared library, install the named library from your distribution. Use `--no-gui` as a browser fallback.
- **No CPU temperature:** inspect `/sys/class/hwmon` and `/sys/class/thermal`; the application deliberately does not add EC commands for temperature.
- **Windows driver not found/untrusted:** install or repair MyASUS, ASUS System Control Interface, and ASUS System Analysis. Unsigned replacement DLLs are rejected.
- **Windows mode is Unknown:** click Restore once. Apply stays blocked until that explicit baseline succeeds.
- **ARM64 release:** hardware control is intentionally unavailable; use `--mock`.
- **EC timeout:** stop making changes, attempt Restore if safe, and reboot. Never retry by scanning commands or registers.

Explicit read-only hardware checks are available only through:

```sh
sudo make hardware-test
```

## Development and contributions

Read [docs/protocol.md](docs/protocol.md), [docs/architecture.md](docs/architecture.md), [docs/security.md](docs/security.md), and `AGENTS.md` before changing hardware code. New models require documented hardware verification; do not infer command compatibility from model similarity.

Keep privileged I/O isolated, preserve finite timeouts and session-owned restore semantics, add mock-backed tests, and run `make test` before submitting changes.

## Releases

GitHub Actions runs on every push, tests the project, and builds Windows x86-64, Windows ARM64, Linux x86-64, and Linux ARM64 archives. To publish them, update `VERSION`, then push the matching tag `vX.Y.Z`. It creates a GitHub Release only for that tag and only if every build succeeds. ARM64 archives are clearly marked GUI/mock-only and never claim unsupported fan access.
