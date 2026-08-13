import pytest

from backend.curve_service import (
    CurveController,
    CurveError,
    interpolate_curve,
    validate_curve_points,
)
from backend.fan_service import FanService
from hardware.mock_backend import MockFanBackend


class MutableTemperature:
    def __init__(self, value=60.0):
        self.value = value

    def get_cpu_temperature(self):
        return self.value


POINTS = [
    {"temperature": 40, "percent": 30},
    {"temperature": 60, "percent": 50},
    {"temperature": 80, "percent": 90},
]


def build_controller(temperature=60.0):
    backend = MockFanBackend()
    service = FanService(
        backend,
        model="ASUS BR1402FGA",
        writes_allowed=True,
        mock_mode=True,
    )
    sensor = MutableTemperature(temperature)
    controller = CurveController(service, sensor, lambda: 60.0)
    return controller, backend, sensor


def test_curve_validation_and_linear_interpolation():
    points = validate_curve_points(POINTS)
    assert interpolate_curve(points, 20) == 30
    assert interpolate_curve(points, 50) == 40
    assert interpolate_curve(points, 70) == 70
    assert interpolate_curve(points, 100) == 90


@pytest.mark.parametrize(
    "points",
    [
        [],
        [{"temperature": 40, "percent": 30}],
        [{"temperature": 50, "percent": 50}, {"temperature": 40, "percent": 60}],
        [{"temperature": 40, "percent": 60}, {"temperature": 60, "percent": 50}],
        [{"temperature": 10, "percent": 20}, {"temperature": 60, "percent": 50}],
        [{"temperature": 40, "percent": 0}, {"temperature": 60, "percent": 50}],
    ],
)
def test_invalid_curve_points_are_rejected(points):
    with pytest.raises(CurveError):
        validate_curve_points(points)


def test_curve_start_applies_target_and_stop_restores_owned_mode():
    controller, backend, _ = build_controller(70.0)
    state = controller.start(0, POINTS, "Workload")
    assert state["active"] is True
    assert state["target_percent"] == 70
    assert backend.test_modes[0] is True
    stopped = controller.stop(restore=True)
    assert stopped["active"] is False
    assert backend.test_modes[0] is False


def test_curve_does_not_restore_manual_mode_it_did_not_establish():
    controller, backend, _ = build_controller(60.0)
    backend.test_modes[0] = True
    controller.start(0, POINTS, "External manual")
    controller.stop(restore=True)
    assert backend.test_modes[0] is True


def test_curve_refuses_to_start_without_temperature():
    controller, backend, _ = build_controller(None)
    with pytest.raises(CurveError) as caught:
        controller.start(0, POINTS)
    assert caught.value.code == "TEMPERATURE_UNAVAILABLE"
    assert backend.test_modes[0] is False
