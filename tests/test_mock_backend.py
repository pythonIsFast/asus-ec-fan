import pytest

from hardware.mock_backend import MockFanBackend


def test_mock_manual_and_restore_follow_verified_order():
    backend = MockFanBackend()
    backend.set_percent(0, 60)
    assert backend.operations == [
        ("select", 0),
        ("enable-test-mode", 0),
        ("set-pwm", 0, 60),
    ]
    assert backend.get_test_mode(0) is True

    backend.operations.clear()
    backend.restore(0)
    assert backend.operations == [
        ("select", 0),
        ("disable-test-mode", 0),
        ("set-pwm", 0, 0),
    ]
    assert backend.test_modes[0] is False


def test_mock_rejects_invalid_fan_without_side_effects():
    backend = MockFanBackend()
    with pytest.raises(ValueError):
        backend.set_percent(1, 60)
    assert backend.operations == []
