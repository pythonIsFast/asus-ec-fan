# Security model

Embedded-controller access can hang a machine, defeat thermal policy, or damage hardware when incorrect commands are used. This project reduces exposure but cannot make EC modification risk-free.

## Unprivileged desktop process

The Flask server and pywebview window refuse to run as root. They do not call Linux port-I/O APIs. Only the small native helper obtains access to exactly the contiguous ports `0x25c` and `0x25d` with `ioperm()`.

Do not make the helper setuid. The recommended installation uses a root-owned binary plus a narrow `sudoers` entry. The Python client calls it with `sudo -n`, so the GUI never opens an interactive privilege prompt or retains root privileges.

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

There is no raw port, packet, register, or command interface. Arguments are decimal integers with tight bounds, fan indices are checked against the live verified fan count, and the helper independently checks DMI before either write command. Errors are JSON. Each invocation drops I/O permission before exiting.

The sudo rule trusts this helper's restricted parser, so the installed binary and its parent directory must remain root-owned and not writable by ordinary users.

## Local HTTP API

Flask is hard-coded to `127.0.0.1`; `LocalServer` rejects any other bind address. Mutation endpoints require a random per-process token embedded in the same-origin UI. Strict JSON bodies reject extra fields. There is no CORS enablement, production debug mode is off, and responses set a restrictive Content Security Policy plus frame, MIME-sniffing, and referrer protections.

Local-only HTTP is still not a general authorization boundary against a compromised user session. Do not expose or proxy this port to a network.

## Restore and failure limits

Clean shutdown restores firmware control only for fans that this session moved from firmware mode into test mode. This avoids overwriting a state established by another application or a previous session. Explicit Restore remains visible in the UI.

SIGINT, SIGTERM, pywebview closure, and normal exit share the cleanup routine. A hard crash, kernel failure, forced power-off, helper termination between EC transactions, or power loss may prevent cleanup. If behavior is unexpected, stop using manual control, use Restore, and reboot so firmware can reinitialize the platform.

Unit tests use only mocks. `make hardware-test` must be run explicitly as root and performs read-only helper checks; it never enables test mode.
