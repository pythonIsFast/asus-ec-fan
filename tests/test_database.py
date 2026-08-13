import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from backend.database import Database


def test_settings_are_persisted_and_merged_with_defaults(tmp_path):
    path = tmp_path / "settings.db"
    database = Database(path)
    updated = database.update_settings({"poll_interval_ms": 1500, "telemetry_enabled": True})
    assert updated["poll_interval_ms"] == 1500
    assert updated["window_width"] == 1120
    assert Database(path).get_settings()["telemetry_enabled"] is True


@pytest.mark.parametrize(
    "payload",
    [None, [], {"unknown": 1}, {"poll_interval_ms": 10}, {"telemetry_enabled": 1}],
)
def test_invalid_settings_are_rejected(tmp_path, payload):
    database = Database(tmp_path / "settings.db")
    with pytest.raises(ValueError):
        database.update_settings(payload)


def test_telemetry_is_optional_and_retained(tmp_path):
    database = Database(tmp_path / "telemetry.db")
    database.add_telemetry(0, 3800, "firmware", 60.0)
    assert database.get_history() == []

    database.update_settings({"telemetry_enabled": True, "telemetry_retention_days": 1})
    old = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            """INSERT INTO telemetry(recorded_at, fan_index, rpm, mode, cpu_temperature)
               VALUES (?, 0, 1000, 'firmware', 50.0)""",
            (old,),
        )
    database.add_telemetry(0, 3900, "manual", 61.0)
    history = database.get_history()
    assert len(history) == 1
    assert history[0]["rpm"] == 3900
