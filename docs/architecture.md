# Architecture

The application keeps privileged hardware access separate from the desktop process:

```text
pywebview window
    -> vanilla HTML/CSS/JavaScript
    -> HTTP on 127.0.0.1 (Flask)
    -> FanService / ProfileService / CurveController
    -> NativeHelperBackend
    -> sudo -n asus-ec-fan-helper
    -> ports 0x25c and 0x25d
```

`app.py` starts Flask on a configurable or automatically selected localhost port and points pywebview at that URL. The same URL can be opened in a regular browser with `--no-gui`. Flask debug mode is never enabled.

An advisory lock beside the SQLite database permits only one application process per user data directory. The native helper separately serializes individual EC operations across processes.

## Layers

- `frontend/` contains static, framework-free presentation and uses `fetch()` for the local API.
- `backend/api.py` validates HTTP shapes and requires a per-process token for every mutation.
- `backend/fan_service.py` owns transitions, fan validation, model write policy, locking, and clean-shutdown restoration.
- `backend/curve_service.py` implements an explicitly started userspace loop. It validates 2–8 monotonic points, reads Linux temperature, interpolates duty, and delegates only fixed-duty writes to `FanService`.
- `backend/profile_service.py` applies persistent firmware, fixed-duty, or curve profiles and ensures only one control strategy is active.
- `backend/database.py` persists settings, profiles, events, and optional bounded telemetry. It is not a cache of hardware truth.
- `backend/temperature_service.py` reads ordinary Linux hwmon or thermal-zone data.
- `hardware/helper_client.py` is the only subprocess boundary.
- `hardware/mock_backend.py` simulates the interface without I/O privileges.
- `helper/` is the only code allowed to call `ioperm()`, `inb()`, or `outb()`.

Each helper invocation takes an exclusive process lock, validates DMI independently for writes, obtains permission for only ports `0x25c`–`0x25d`, performs one fixed high-level request, verifies mode-changing requests by reading test mode back, drops I/O permission, and exits. Python additionally verifies the resulting mode through the backend abstraction before updating application state.

Successful helper JSON includes a small helper-API version. The Python client rejects missing or incompatible versions with an installation instruction, preventing an older installed helper from silently retaining obsolete EC transaction behavior.

## Compatibility

Supported model names are centralized in `backend/config.py`. DMI product name is read from `/sys/class/dmi/id/product_name`; the BR1402FGA firmware string `ASUS BR1402FGA_BR1402FGA` is explicitly included. Reads may be attempted for diagnostics on an unknown model, but `FanService` blocks both manual and restore writes unless the model is whitelisted. The native helper repeats this check independently. Explicit mock mode permits simulated writes.

Adding a model requires hardware verification, a protocol-document update, tests, and then a whitelist entry. It must not involve automatic register or command probing.

## State and shutdown

Live RPM, test mode, and temperature always come from the backend. SQLite stores preferences, profile definitions, events, and optional samples, never the current hardware state. Profiles are not automatically applied at launch.

Before entering manual mode, the service reads current test mode. A fan is marked session-owned only when this process changed it from firmware to manual. A write is not reported as successful until test mode reads back as enabled. Restore likewise must read back as firmware mode. The curve controller remembers whether it started from firmware and restores only that owned transition. Direct manual/restore actions stop the curve first. SIGINT, SIGTERM, normal interpreter exit, and pywebview close all call one idempotent cleanup path. Cleanup restores only session-owned fans. An explicitly clicked Restore action is always honored on supported hardware.
