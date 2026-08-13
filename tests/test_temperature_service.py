from backend.temperature_service import TemperatureService


def test_temperature_prefers_cpu_label(tmp_path):
    hwmon = tmp_path / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (hwmon / "temp1_input").write_text("45000\n", encoding="utf-8")
    (hwmon / "temp1_label").write_text("GPU\n", encoding="utf-8")
    (hwmon / "temp2_input").write_text("67000\n", encoding="utf-8")
    (hwmon / "temp2_label").write_text("Package id 0\n", encoding="utf-8")
    service = TemperatureService(tmp_path / "hwmon", tmp_path / "thermal")
    assert service.get_cpu_temperature() == 67.0
