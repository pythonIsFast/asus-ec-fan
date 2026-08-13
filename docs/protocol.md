# Verified ASUS EC fan protocol

This document is intentionally limited. It records only the fan operations already tested on an ASUS BR1402FGA. It is not a general ASUS EC reference and must not be used as a reason to scan registers or try nearby command values.

## Verified

### Hardware interface

| Purpose | Port |
| --- | ---: |
| Data | `0x25c` |
| Status / command | `0x25d` |

Status bit 0 is OBF (output buffer full). Status bit 1 is IBF (input buffer full). Operations wait for IBF to clear before writes and wait for OBF before reading a reply. Stale OBF data is drained before a transaction. All waits have finite deadlines.

The ASUS fan command is `0xdd`. A transaction sends `0xdd` to the command port, followed by one of the verified three-byte payloads through the data port. The implementation never accepts command bytes from a caller.

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

Fan-specific reads select the validated fan first. RPM is assembled as:

```text
rpm = (high << 8) | low
```

Percentage is clamped and validated at 1–100 in the application. The helper converts it with integer round-to-nearest behavior:

```text
pwm = round(percent / 100 * 255)
```

Verified observations on BR1402FGA:

- Fan count is 1.
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

If the PWM transaction fails after enabling test mode, the helper makes a best-effort attempt to send the verified disable-test-mode payload before returning an error.

### Restore

The implemented restore path is:

```text
DD : 82 32 <fan>
DD : 82 31 00
```

The critical verified action is disabling ASUS test mode.

## Inferred or implementation policy

- A fan count outside 1–8 is treated as invalid rather than trusted.
- A nonzero test-mode reply is represented as enabled.
- A 200 ms per-wait deadline and a 64-byte drain ceiling are conservative software safety limits; they are not claims about EC timing guarantees.
- The helper re-reads fan count before every fan-specific command to validate the index against current hardware state.

## Unknown

- No behavior is claimed for models other than the whitelisted ASUS BR1402FGA.
- Multi-fan behavior has not been verified on the initial machine.
- The repository did not contain the earlier proof of concept mentioned in the project brief. That proof of concept reportedly wrote PWM 0 while restoring, but the necessity and ordering of that extra write could not be reviewed. This implementation does not reproduce it because disabling test mode is verified and unnecessary EC writes are prohibited.
- Crash and power-loss recovery cannot be guaranteed. Clean shutdown performs session-owned restoration.
- No additional EC commands, registers, fan curves, or diagnostic modes are known or permitted.
