# AGENTS.md

This project controls the CPU fan on verified ASUS laptops under Linux.

Read `docs/protocol.md` before touching EC communication code.

## Safety constraints

- Never write arbitrary EC commands or arbitrary I/O ports.
- Only use ports 0x25c and 0x25d.
- Never invent EC commands.
- Never add automatic EC register or command scanning.
- Preserve the EC handshake and timeouts.
- Always provide a way to return fan control to firmware.
- Never enable fan test mode without a corresponding restore path.
- Never perform hardware writes in tests.
- Unit tests must use a mocked I/O backend.
- Hardware tests must require explicit root invocation.
- Preserve session-owned restore-to-firmware behavior.
- Keep privileged hardware access isolated in the native helper.
- Keep the GUI and Flask process unprivileged and localhost-only.
- Run `make test` before finishing.
