# Security model

Embedded-controller access can hang a machine, defeat thermal policy, or damage hardware when incorrect commands are used. This project reduces exposure but cannot make EC modification risk-free.

## Unprivileged desktop process

The Flask server and pywebview window refuse to run as root. They do not call Linux port-I/O APIs. Only the small native helper obtains access to exactly the contiguous ports `0x25c` and `0x25d` with `ioperm()`.

Do not make the helper setuid. The supported installation uses a root-owned binary, a dedicated `asus-ec-fan` group, and a narrow validated `sudoers` entry. The Python client calls it with `sudo -n`, so the GUI never opens an interactive privilege prompt or retains root privileges.

## Restricted helper

The helper accepts only:

```text
status
fan-count
rpm <fan>
test-mode <fan>
set <fan> <percent>
restore <fan>
```

There is no raw port, packet, register, or command interface. Arguments are decimal integers with tight bounds, fan indices are checked against the live verified fan count, and the helper independently checks DMI before either write command. Helper processes take an exclusive root-owned lock so two application requests cannot interleave. Mode-changing commands are read back before success is returned. Errors are JSON. Each invocation drops I/O permission before exiting.

The sudo rule trusts this helper's restricted parser, so the installed binary and its parent directory must remain root-owned and not writable by ordinary users. The Python client checks the installed file type, executable bit, ownership, and write permissions before invoking sudo; it never automatically elevates the build artifact in the user-writable project directory.

## Local HTTP API

Flask is hard-coded to `127.0.0.1`; `LocalServer` rejects any other bind address. Mutation endpoints require a random per-process token embedded in the same-origin UI. Strict JSON bodies reject extra fields. Curve and profile endpoints accept only validated high-level fan percentages and temperature points; they cannot carry raw ports, EC commands, or packets. There is no CORS enablement, production debug mode is off, and responses set a restrictive Content Security Policy plus frame, MIME-sniffing, and referrer protections. Inline scripts remain prohibited; inline CSS is allowed because pywebview injects a small runtime style into the page.

Local-only HTTP is still not a general authorization boundary against a compromised user session. Do not expose or proxy this port to a network.

## Restore and failure limits

Clean shutdown restores firmware control only for fans that this session moved from firmware mode into test mode. This avoids overwriting a state established by another application or a previous session. Explicit Restore remains visible in the UI.

SIGINT, SIGTERM, pywebview closure, and normal exit share the cleanup routine. A hard crash, kernel failure, forced power-off, helper termination between EC transactions, or power loss may prevent cleanup. If behavior is unexpected, stop using manual control, use Restore, and reboot so firmware can reinitialize the platform.

Temperature curves are a userspace loop and must be started explicitly; saved profiles never auto-apply at startup. Invalid or unavailable temperature stops the controller. When the controller itself moved the EC from firmware to test mode, normal stop and clean shutdown attempt to restore it. If test mode pre-existed, the controller does not claim ownership and does not restore that external state automatically.

Unit tests use only mocks, including a compiled C I/O simulation. `make hardware-test` must be run explicitly as root and performs read-only helper checks; it never enables test mode.
