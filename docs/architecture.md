# Architecture

The application keeps privileged hardware access separate from the desktop process:

```text
pywebview window
    -> vanilla HTML/CSS/JavaScript
    -> HTTP on 127.0.0.1 (Flask)
    -> FanService
    -> NativeHelperBackend
    -> sudo -n asus-ec-fan-helper
    -> ports 0x25c and 0x25d
```

`app.py` starts Flask on a configurable or automatically selected localhost port and points pywebview at that URL. The same URL can be opened in a regular browser with `--no-gui`. Flask debug mode is never enabled.

## Layers

- `frontend/` contains static, framework-free presentation and uses `fetch()` for the local API.
- `backend/api.py` validates HTTP shapes and requires a per-process token for every mutation.
- `backend/fan_service.py` owns transitions, fan validation, model write policy, locking, and clean-shutdown restoration.
- `backend/database.py` persists settings, events, and optional bounded telemetry. It is not a cache of hardware truth.
- `backend/temperature_service.py` reads ordinary Linux hwmon or thermal-zone data.
- `hardware/helper_client.py` is the only subprocess boundary.
- `hardware/mock_backend.py` simulates the interface without I/O privileges.
- `helper/` is the only code allowed to call `ioperm()`, `inb()`, or `outb()`.

## Compatibility

Supported model names are centralized in `backend/config.py`. DMI product name is read from `/sys/class/dmi/id/product_name`. Reads may be attempted for diagnostics on an unknown model, but `FanService` blocks both manual and restore writes unless the model is whitelisted. Explicit mock mode permits simulated writes.

Adding a model requires hardware verification, a protocol-document update, tests, and then a whitelist entry. It must not involve automatic register or command probing.

## State and shutdown

Live RPM, test mode, and temperature always come from the backend. SQLite stores preferences and optional samples only.

Before entering manual mode, the service reads current test mode. A fan is marked session-owned only when this process changed it from firmware to manual. SIGINT, SIGTERM, normal interpreter exit, and pywebview close all call one idempotent cleanup path. Cleanup restores only session-owned fans. An explicitly clicked Restore action is always honored on supported hardware.
