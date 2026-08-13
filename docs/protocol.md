# Verified ASUS EC fan protocol

This document is intentionally limited. It records only the fan operations already tested on an ASUS BR1402FGA. It is not a general ASUS EC reference and must not be used as a reason to scan registers or try nearby command values.

## Verified

### Hardware interface

| Purpose | Port |
| --- | ---: |
| Data | `0x25c` |
| Status / command | `0x25d` |

Status bit 0 is OBF (output buffer full). Status bit 1 is IBF (input buffer full). Operations wait for IBF to clear before writes and wait for OBF before reading a reply. Stale OBF data is drained before a transaction. All waits have finite deadlines.

The ASUS fan command is `0xdd`. The working legacy implementation supplied with the project shows that every transaction first sends `0xff` and then `0xdd` to the command/status port. Omitting `0xff` can make a transaction appear to complete without changing the fan. The selected three-byte payload then goes through the data port. The implementation never accepts command bytes from a caller.

```text
command port: FF
command port: DD
data port:    <payload byte 0>
data port:    <payload byte 1>
data port:    <payload byte 2>
```

### Payloads

| Operation | Payload | Reply |
| --- | --- | --- |
| Select fan | `82 32 <fan_index>` | none |
| Enable fan test mode | `82 31 01` | none |
| Disable test mode | `82 31 00` | none |
| Set PWM duty | `82 35 <0..255>` | none |
| Read fan count | `02 30 00` | one byte |
| Read test mode | `02 31 00` | one byte |
| Read RPM low byte | `02 33 00` | one byte |
| Read RPM high byte | `02 34 00` | one byte |

Fan-specific reads select the validated fan first. The working implementation reads the high byte (`0x34`) before the low byte (`0x33`). RPM is assembled as:

```text
rpm = (high << 8) | low
```

Percentage is clamped and validated at 1–100 in the application. The helper converts it with integer round-to-nearest behavior:

```text
pwm = round(percent / 100 * 255)
```

Verified observations on BR1402FGA:

- Fan count is 1.
- The target machine reports DMI product name `ASUS BR1402FGA_BR1402FGA`.
- EC RPM agreed closely with `lm-sensors` (3850 RPM versus 3800 RPM in one reading).
- Manual duty worked at 60% (`0x99`) and 100% (`0xff`).
- Disabling test mode restored firmware fan control.

### Manual control

The verified order is:

```text
DD : 82 32 <fan>
DD : 82 31 01
DD : 82 35 <pwm>
```

Before the write sequence, the helper reads whether test mode was already enabled. If this invocation started from firmware mode and the PWM transaction or subsequent verification fails, it makes a best-effort restore. It does not disable a manual mode that predated the invocation. After a successful write sequence, the helper reads test mode back and reports success only when the EC confirms manual mode.

### Restore

The implemented restore path is:

```text
DD : 82 32 <fan>
DD : 82 31 00
DD : 82 35 00
```

The critical verified action is disabling ASUS test mode. The working legacy implementation then sends PWM 0, documented there as ignored once firmware control resumes. The helper preserves that complete known-good sequence and verifies that test mode reads back as disabled.

## Inferred or implementation policy

- A fan count outside 1–8 is treated as invalid rather than trusted.
- A nonzero test-mode reply is represented as enabled.
- IBF and stale-OBF draining use 100 µs polling with a 1000-poll ceiling, matching the supplied working implementation.
- The final OBF wait for a one-byte read uses the working implementation's approximately 5 ms window and retries the complete read transaction once on that final timeout.
- The helper re-reads fan count before every fan-specific command to validate the index against current hardware state.
- Helper processes serialize access with `/run/lock/asus-ec-fan.lock`. This cannot serialize against firmware or kernel EC users.

## Unknown

- No behavior is claimed for models other than the whitelisted ASUS BR1402FGA.
- Multi-fan behavior has not been verified on the initial machine.
- Crash and power-loss recovery cannot be guaranteed. Clean shutdown performs session-owned restoration.
- No additional EC commands, registers, fan curves, or diagnostic modes are known or permitted.
