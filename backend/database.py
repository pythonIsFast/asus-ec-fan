from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "poll_interval_ms": 2000,
    "telemetry_enabled": False,
    "telemetry_retention_days": 7,
    "last_selected_fan": 0,
    "window_width": 1120,
    "window_height": 760,
}


def validate_settings(values: object) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise ValueError("Settings must be a JSON object")
    allowed = set(DEFAULT_SETTINGS)
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Unknown setting: {sorted(unknown)[0]}")

    validated: dict[str, Any] = {}
    for key, value in values.items():
        if key == "telemetry_enabled":
            if not isinstance(value, bool):
                raise ValueError("telemetry_enabled must be true or false")
        elif isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        elif key == "poll_interval_ms" and not 500 <= value <= 60000:
            raise ValueError("poll_interval_ms must be between 500 and 60000")
        elif key == "telemetry_retention_days" and not 1 <= value <= 365:
            raise ValueError("telemetry_retention_days must be between 1 and 365")
        elif key == "last_selected_fan" and not 0 <= value <= 7:
            raise ValueError("last_selected_fan must be between 0 and 7")
        elif key in {"window_width", "window_height"} and not 320 <= value <= 4096:
            raise ValueError(f"{key} must be between 320 and 4096")
        validated[key] = value
    return validated


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    fan_index INTEGER NOT NULL,
                    rpm INTEGER,
                    mode TEXT,
                    cpu_temperature REAL
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_recorded_at
                    ON telemetry(recorded_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    mode TEXT NOT NULL CHECK(mode IN ('firmware', 'manual', 'curve')),
                    percent INTEGER,
                    curve_json TEXT,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            now = datetime.now(UTC).isoformat()
            connection.executemany(
                """INSERT OR IGNORE INTO profiles
                   (name, mode, percent, curve_json, built_in, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                [
                    ("Balanced", "firmware", None, None, now, now),
                    ("Fixed 60%", "manual", 60, None, now, now),
                    (
                        "Temperature curve",
                        "curve",
                        None,
                        json.dumps(
                            [
                                {"temperature": 45, "percent": 30},
                                {"temperature": 60, "percent": 50},
                                {"temperature": 75, "percent": 75},
                                {"temperature": 90, "percent": 100},
                            ]
                        ),
                        now,
                        now,
                    ),
                ],
            )

    def get_settings(self) -> dict[str, Any]:
        result = dict(DEFAULT_SETTINGS)
        with self._connect() as connection:
            rows = connection.execute("SELECT key, value_json FROM settings").fetchall()
        for row in rows:
            if row["key"] in DEFAULT_SETTINGS:
                result[row["key"]] = json.loads(row["value_json"])
        return result

    def update_settings(self, values: object) -> dict[str, Any]:
        validated = validate_settings(values)
        with self._lock, self._connect() as connection:
            connection.executemany(
                """INSERT INTO settings(key, value_json) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json""",
                [(key, json.dumps(value)) for key, value in validated.items()],
            )
        return self.get_settings()

    def add_event(self, event_type: str, details: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO events(recorded_at, event_type, details_json) VALUES (?, ?, ?)",
                (datetime.now(UTC).isoformat(), event_type, json.dumps(details)),
            )

    def add_telemetry(
        self, fan_index: int, rpm: int | None, mode: str, cpu_temperature: float | None
    ) -> None:
        settings = self.get_settings()
        if not settings["telemetry_enabled"]:
            return
        now = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO telemetry
                   (recorded_at, fan_index, rpm, mode, cpu_temperature)
                   VALUES (?, ?, ?, ?, ?)""",
                (now.isoformat(), fan_index, rpm, mode, cpu_temperature),
            )
            cutoff = now - timedelta(days=settings["telemetry_retention_days"])
            connection.execute(
                "DELETE FROM telemetry WHERE recorded_at < ?", (cutoff.isoformat(),)
            )

    def get_history(self, limit: int = 250) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 1000)
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT recorded_at, fan_index, rpm, mode, cpu_temperature
                   FROM telemetry ORDER BY recorded_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _profile_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "mode": row["mode"],
            "percent": row["percent"],
            "curve_points": json.loads(row["curve_json"]) if row["curve_json"] else None,
            "built_in": bool(row["built_in"]),
        }

    def get_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, name, mode, percent, curve_json, built_in
                   FROM profiles ORDER BY built_in DESC, id ASC"""
            ).fetchall()
        return [self._profile_row(row) for row in rows]

    def get_profile(self, profile_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT id, name, mode, percent, curve_json, built_in
                   FROM profiles WHERE id = ?""",
                (profile_id,),
            ).fetchone()
        return self._profile_row(row) if row else None

    def create_profile(
        self,
        name: str,
        mode: str,
        percent: int | None,
        curve_points: list[dict[str, int]] | None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO profiles
                   (name, mode, percent, curve_json, built_in, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?)""",
                (
                    name,
                    mode,
                    percent,
                    json.dumps(curve_points) if curve_points is not None else None,
                    now,
                    now,
                ),
            )
            profile_id = cursor.lastrowid
        profile = self.get_profile(int(profile_id))
        assert profile is not None
        return profile

    def delete_profile(self, profile_id: int) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM profiles WHERE id = ? AND built_in = 0", (profile_id,)
            )
        return cursor.rowcount > 0
