from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class ApplicationAlreadyRunning(RuntimeError):
    pass


class ApplicationLock:
    """Advisory single-instance lock held for the desktop process lifetime."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._file: TextIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.path.open("a+", encoding="ascii")
        try:
            if os.name == "nt":
                lock_file.seek(0)
                if lock_file.read(1) == "":
                    lock_file.write("0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            lock_file.close()
            raise ApplicationAlreadyRunning(
                "Another ASUS EC Fan process is already running"
            ) from exc
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"{os.getpid()}\n")
        lock_file.flush()
        self._file = lock_file

    def release(self) -> None:
        if self._file is None:
            return
        if os.name == "nt":
            self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None
