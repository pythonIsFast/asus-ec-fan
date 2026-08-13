import pytest

from backend.curve_service import CurveController
from backend.database import Database
from backend.fan_service import FanService
from backend.profile_service import ProfileError, ProfileService
from hardware.mock_backend import MockFanBackend


class FixedTemperature:
    def get_cpu_temperature(self):
        return 65.0


def build_services(tmp_path):
    database = Database(tmp_path / "profiles.db")
    backend = MockFanBackend()
    fan_service = FanService(
        backend, model="ASUS BR1402FGA", writes_allowed=True, mock_mode=True
    )
    controller = CurveController(fan_service, FixedTemperature(), lambda: 60.0)
    profiles = ProfileService(database, fan_service, controller)
    return database, backend, controller, profiles


def test_builtin_profiles_exist_and_apply(tmp_path):
    _, backend, controller, profiles = build_services(tmp_path)
    items = profiles.list_profiles()["profiles"]
    assert [item["name"] for item in items[:3]] == [
        "Balanced",
        "Fixed 60%",
        "Temperature curve",
    ]
    manual = next(item for item in items if item["mode"] == "manual")
    result = profiles.apply(manual["id"])
    assert result["profile"]["name"] == "Fixed 60%"
    assert backend.percents[0] == 60
    firmware = next(item for item in items if item["mode"] == "firmware")
    profiles.apply(firmware["id"])
    assert backend.test_modes[0] is False
    controller.stop(restore=True)


def test_custom_curve_profile_persists_applies_and_deletes(tmp_path):
    database, backend, controller, profiles = build_services(tmp_path)
    created = profiles.create(
        {
            "name": "Office curve",
            "mode": "curve",
            "curve_points": [
                {"temperature": 40, "percent": 25},
                {"temperature": 80, "percent": 85},
            ],
        }
    )
    assert Database(database.path).get_profile(created["id"])["name"] == "Office curve"
    profiles.apply(created["id"])
    assert controller.status()["active"] is True
    assert backend.test_modes[0] is True
    controller.stop(restore=True)
    profiles.clear_active_curve()
    profiles.delete(created["id"])
    assert database.get_profile(created["id"]) is None


def test_builtin_and_active_profiles_cannot_be_deleted(tmp_path):
    _, _, controller, profiles = build_services(tmp_path)
    built_in = profiles.list_profiles()["profiles"][0]
    with pytest.raises(ProfileError) as caught:
        profiles.delete(built_in["id"])
    assert caught.value.code == "PROFILE_BUILT_IN"
    controller.stop(restore=True)
