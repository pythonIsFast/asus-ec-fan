import pytest

from backend.fan_service import FanService, FanServiceError
from hardware.helper_client import HardwareError
from hardware.mock_backend import MockFanBackend


def make_service(backend=None, *, writes_allowed=True):
    return FanService(
        backend or MockFanBackend(),
        model="ASUS BR1402FGA",
        writes_allowed=writes_allowed,
        mock_mode=isinstance(backend, MockFanBackend) if backend else True,
    )


def test_manual_transition_and_explicit_restore():
    backend = MockFanBackend()
    service = make_service(backend)
    assert service.set_manual(0, 60) == {
        "ok": True,
        "fan": 0,
        "mode": "manual",
        "percent": 60,
    }
    fan = service.get_fan(0)
    assert fan["mode"] == "manual"
    assert fan["session_owned"] is True

    assert service.restore(0)["mode"] == "firmware"
    assert service.restore_session_owned() == []
    assert backend.test_modes[0] is False


def test_shutdown_restores_only_mode_established_by_session():
    backend = MockFanBackend()
    backend.test_modes[0] = True
    service = make_service(backend)
    service.set_manual(0, 70)
    backend.operations.clear()

    assert service.restore_session_owned() == []
    assert backend.operations == []
    assert backend.test_modes[0] is True


def test_shutdown_restores_owned_mode():
    backend = MockFanBackend()
    service = make_service(backend)
    service.set_manual(0, 70)
    backend.operations.clear()
    service.restore_session_owned()
    assert backend.operations == [("select", 0), ("disable-test-mode", 0)]


def test_unknown_hardware_blocks_write_before_hardware_change():
    backend = MockFanBackend()
    service = make_service(backend, writes_allowed=False)
    with pytest.raises(FanServiceError) as caught:
        service.set_manual(0, 60)
    assert caught.value.code == "UNSUPPORTED_HARDWARE"
    assert backend.operations == []


def test_hardware_error_is_clear_and_finite():
    backend = MockFanBackend()
    backend.failure = HardwareError("EC_TIMEOUT_OBF", "Timed out")
    service = make_service(backend)
    with pytest.raises(FanServiceError) as caught:
        service.get_fans()
    assert caught.value.code == "EC_TIMEOUT_OBF"
    assert caught.value.status_code == 503


def test_failed_manual_transition_attempts_restore():
    class FailsAfterEnable(MockFanBackend):
        def set_percent(self, fan_index, percent):
            self.test_modes[fan_index] = True
            self.operations.extend(
                [("select", fan_index), ("enable-test-mode", fan_index), ("pwm-failed",)]
            )
            raise HardwareError("EC_TIMEOUT_IBF", "PWM write timed out")

    backend = FailsAfterEnable()
    service = make_service(backend)
    with pytest.raises(FanServiceError):
        service.set_manual(0, 60)
    assert backend.test_modes[0] is False
    assert backend.operations[-2:] == [("select", 0), ("disable-test-mode", 0)]
    assert service.restore_session_owned() == []
