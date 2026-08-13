# AGENTS.md

This project controls the CPU fan on verified ASUS laptops under Linux and Windows.

Read `docs/protocol.md` before touching EC communication code.

## Mandatory Git workflow

Follow this workflow for every implementation task, in exactly this order:

1. At the beginning of the task, run `git pull --rebase` before changing any files.
2. If the pull and rebase complete successfully, continue to step 3. If they fail, produce conflicts, or leave the repository in an unclear state, stop immediately and inform the user. Do not start coding and do not resolve conflicts by guessing.
3. Implement the requested changes.
4. Stage the completed changes with `git add .`.
5. Commit them with a concise, descriptive message using `git commit -m "Short commit message"`.
6. Push the commit with `git push`.
7. Report that the task is finished only after the push succeeds. If staging, committing, or pushing fails, inform the user instead of claiming completion.

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
- Never bundle, download, or replace the proprietary ASUS Windows DLL.
- Keep Windows driver access isolated in the narrow helper and require signature verification.
- Keep the GUI and Flask process unprivileged and localhost-only.
- Run `make test` before finishing.
