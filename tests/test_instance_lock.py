import pytest

from backend.instance_lock import ApplicationAlreadyRunning, ApplicationLock


def test_application_lock_allows_only_one_process_instance(tmp_path):
    path = tmp_path / "app.lock"
    first = ApplicationLock(path)
    second = ApplicationLock(path)
    first.acquire()
    try:
        with pytest.raises(ApplicationAlreadyRunning):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()
