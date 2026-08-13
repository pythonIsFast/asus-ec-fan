# ASUS EC Fan

ASUS EC Fan is a small Linux desktop application for reading and explicitly controlling the CPU fan on verified ASUS laptops whose normal Linux fan-curve interface is unavailable. The first supported system is the **ASUS BR1402FGA**.

> **Warning:** This application accesses embedded-controller hardware. Incorrect EC access can destabilize or damage a machine. Only the documented BR1402FGA protocol is implemented. Unknown models are write-blocked by default.

The GUI shows the detected model, CPU temperature, current RPM, and whether ASUS fan test/manual mode is active. A slider prepares a percentage, but no hardware change occurs until **Apply manual speed** is selected. **Restore firmware control** disables ASUS test mode.

## Status

First usable milestone:

- Linux, Python 3, Flask, SQLite, pywebview
- framework-free HTML, CSS, and JavaScript
- minimal native C helper for ports `0x25c` and `0x25d`
- one verified model: ASUS BR1402FGA
- safe mock mode for development
- localhost-only, token-protected mutation API
- optional telemetry with retention cleanup

Screenshot placeholder: capture the application on verified BR1402FGA hardware after installation.

## Requirements

- Linux on x86 with GCC or Clang and development headers
- Python 3.10 or newer with `venv`
- pywebview runtime dependencies for GTK or Qt (distribution-specific)
- `sudo` configured for the installed helper
- verified ASUS BR1402FGA for real writes

Common Debian/Ubuntu GUI packages are `python3-venv`, `build-essential`, `python3-gi`, `gir1.2-webkit2-4.1`, and `gir1.2-gtk-3.0`. Package names vary by distribution.

## Build and test

```sh
make setup
make
make test
```

`make test` is hardware-safe. It uses the mock backend and never invokes the compiled helper, `ioperm`, `inb`, or `outb`.

To build only the native helper:

```sh
make helper
```

## Install privileged helper

Build and install the helper as a root-owned, non-setuid executable:

```sh
sudo install -d -o root -g root -m 0755 /usr/local/libexec
sudo install -o root -g root -m 0755 helper/asus-ec-fan-helper /usr/local/libexec/asus-ec-fan-helper
```

Create a dedicated local group, add the intended user, and use `visudo` to grant that group permission to execute only this helper. A typical rule is:

```text
%asus-ec-fan ALL=(root) NOPASSWD: /usr/local/libexec/asus-ec-fan-helper *
```

The helper itself accepts only its fixed command vocabulary; nevertheless, keep it and `/usr/local/libexec` root-owned. Log out and back in after changing group membership. Review [the security model](docs/security.md) before installation.

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

The service selects an unused localhost port by default. It never binds to an external interface and the GUI refuses to start as root.

## Manual and restore behavior

Apply performs the verified sequence: select fan, enable ASUS test mode, then set PWM. The percentage range is 1–100 and conversion is validated in both Python and C.

Restore selects the fan and disables ASUS test mode. If this application moved a fan from firmware into manual mode, a clean SIGINT, SIGTERM, window close, or normal shutdown attempts the same restore. It does not automatically restore a test mode that was already active before this session.

A crash or power loss can prevent cleanup. Always keep the Restore action accessible, and reboot if firmware ownership is uncertain.

## Settings and telemetry

SQLite data defaults to `${XDG_DATA_HOME}/asus-ec-fan/app.db` or `~/.local/share/asus-ec-fan/app.db`. Settings include polling interval, telemetry toggle and retention, selected fan, and window dimensions.

Telemetry is disabled by default. When enabled it records at most one sample per fan every 10 seconds (or the longer configured poll interval) and removes data older than the retention period.

## Troubleshooting

- **Unsupported hardware:** DMI model must be `ASUS BR1402FGA` or `BR1402FGA`. Unknown systems remain read-only. Use `--mock` for UI development.
- **Helper unavailable:** build it, install it at `/usr/local/libexec/asus-ec-fan-helper`, and verify the sudoers rule with `sudo -n /usr/local/libexec/asus-ec-fan-helper status`.
- **Permission denied:** `ioperm()` requires root/CAP_SYS_RAWIO. Do not run the GUI as root and do not make the helper setuid.
- **No window:** install the distro's GTK/WebKit or Qt dependencies, or use `--no-gui` to open the printed localhost URL.
- **No CPU temperature:** inspect `/sys/class/hwmon` and `/sys/class/thermal`; the application deliberately does not add EC commands for temperature.
- **EC timeout:** stop making changes, attempt Restore if safe, and reboot. Never retry by scanning commands or registers.

Explicit read-only hardware checks are available only through:

```sh
sudo make hardware-test
```

## Development and contributions

Read [docs/protocol.md](docs/protocol.md), [docs/architecture.md](docs/architecture.md), [docs/security.md](docs/security.md), and `AGENTS.md` before changing hardware code. New models require documented hardware verification; do not infer command compatibility from model similarity.

Keep privileged I/O isolated, preserve finite timeouts and session-owned restore semantics, add mock-backed tests, and run `make test` before submitting changes.
