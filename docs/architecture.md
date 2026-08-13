# Architecture

The application keeps hardware access separate from the desktop process:

```text
pywebview window
    -> vanilla HTML/CSS/JavaScript
    -> HTTP on 127.0.0.1 (Flask)
    -> FanService / ProfileService / CurveController
    -> NativeHelperBackend
    -> sudo -n asus-ec-fan-helper
    -> ports 0x25c and 0x25d
```

Windows x86-64 instead uses a separate narrow helper which verifies and loads the officially installed ASUS System Analysis DLL. The DLL is not in this repository or its releases. Windows ARM64 and Linux ARM64 packages provide the desktop UI and mock backend but block unsupported hardware writes.

`app.py` starts Flask on a configurable or automatically selected localhost port and points pywebview at that URL. The same URL can be opened in a regular browser with `--no-gui`. Flask debug mode is never enabled.

An advisory lock beside the SQLite database permits only one application process per user data directory. The native helper separately serializes individual EC operations across processes.

## Layers

- `frontend/` contains static, framework-free presentation and uses `fetch()` for the local API.
- `backend/api.py` validates HTTP shapes and requires a per-process token for every mutation.
- `backend/fan_service.py` owns transitions, fan validation, model write policy, locking, and clean-shutdown restoration.
- `backend/curve_service.py` implements an explicitly started userspace loop. It validates 2–8 monotonic points, reads Linux temperature, interpolates duty, and delegates only fixed-duty writes to `FanService`.
- `backend/profile_service.py` applies persistent firmware, fixed-duty, or curve profiles and ensures only one control strategy is active.
- `backend/database.py` persists settings, profiles, events, and optional bounded telemetry. It is not a cache of hardware truth.
- `backend/temperature_service.py` reads Linux hwmon/thermal-zone data or delegates Windows temperature to the ASUS backend.
- `hardware/helper_client.py` is the only subprocess boundary.
- `hardware/mock_backend.py` simulates the interface without I/O privileges.
- `helper/` is the only code allowed to call `ioperm()`, `inb()`, or `outb()`.
- `windows_helper/` is the only code allowed to load `AsusWinIO64.dll` and exposes fixed operations only.

Each Linux helper invocation takes an exclusive process lock, validates DMI independently for writes, obtains permission for only ports `0x25c`–`0x25d`, performs one fixed high-level request, verifies mode-changing requests by reading test mode back, drops I/O permission, and exits. The Windows helper has a separate named lock and returns only after its fixed driver call completes; because its API lacks mode readback, the response is explicitly marked unverified.

Successful helper JSON includes a small helper-API version. The Python client rejects missing or incompatible versions with an installation instruction, preventing an older installed helper from silently retaining obsolete EC transaction behavior.

## Compatibility

Supported model names are centralized in `backend/config.py`. Linux reads `/sys/class/dmi/id/product_name`; Windows reads `SystemProductName` from the BIOS registry key. The BR1402FGA firmware string `ASUS BR1402FGA_BR1402FGA` is explicitly included. Unknown models remain write-blocked. Linux repeats the check in its helper; Windows additionally requires AMD64 and an ASUS-signed installed driver. Explicit mock mode permits simulated writes.

Adding a model requires hardware verification, a protocol-document update, tests, and then a whitelist entry. It must not involve automatic register or command probing.

## State and shutdown

Live RPM and temperature always come from the backend. Linux also reads live test mode. Windows reports Unknown until explicit Restore, then tracks only commands completed by this process because the known ASUS API lacks test-mode readback. SQLite stores preferences, profiles, events, and optional samples, never current hardware state. Profiles are not automatically applied at launch.

On Linux, the service reads current test mode and verifies mode-changing writes. On Windows, explicit Restore first establishes the process-local baseline; later manual mode is therefore session-owned. The curve controller restores only its owned transition. Direct manual/restore actions stop the curve first. SIGINT, SIGTERM, normal interpreter exit, and pywebview close all call one idempotent cleanup path. Cleanup restores only session-owned fans.
