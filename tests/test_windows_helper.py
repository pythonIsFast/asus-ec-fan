import pytest

from windows_helper.asus_windows_helper import HelperError, execute, percent_to_pwm


class FakeAsusDll:
    def __init__(self, fan_count=1):
        self.count = fan_count
        self.operations = []

    def fan_count(self):
        return self.count

    def select_fan(self, fan):
        self.operations.append(("select", fan))

    def read_rpm(self):
        return 3850

    def read_temperature(self):
        return 51

    def set_test_mode(self, enabled):
        self.operations.append(("test-mode", enabled))

    def set_pwm(self, pwm):
        self.operations.append(("pwm", pwm))


@pytest.mark.parametrize("percent,pwm", [(1, 3), (60, 153), (100, 255)])
def test_windows_percent_conversion(percent, pwm):
    assert percent_to_pwm(percent) == pwm


@pytest.mark.parametrize("value", [0, 101, True, "1.5", "01"])
def test_windows_percent_rejects_malformed_values(value):
    with pytest.raises(HelperError) as error:
        percent_to_pwm(value)
    assert error.value.code == "INVALID_PERCENT"


def test_windows_manual_operation_order_is_fixed():
    dll = FakeAsusDll()
    result = execute(["set", "0", "60"], dll)
    assert result["pwm"] == 153
    assert dll.operations == [("select", 0), ("test-mode", 1), ("pwm", 153)]


def test_windows_restore_preserves_verified_order():
    dll = FakeAsusDll()
    assert execute(["restore", "0"], dll)["mode"] == "firmware"
    assert dll.operations == [("select", 0), ("test-mode", 0), ("pwm", 0)]


@pytest.mark.parametrize("arguments", [["raw-command"], ["write-port", "25c", "ff"], ["set", "0"]])
def test_windows_helper_has_no_raw_or_malformed_commands(arguments):
    with pytest.raises(HelperError) as error:
        execute(arguments, FakeAsusDll())
    assert error.value.code == "INVALID_COMMAND"


def test_windows_helper_validates_fan_before_write():
    dll = FakeAsusDll()
    with pytest.raises(HelperError) as error:
        execute(["set", "1", "60"], dll)
    assert error.value.code == "INVALID_FAN"
    assert dll.operations == []
