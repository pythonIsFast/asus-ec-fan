from backend.api import create_app
from backend.database import Database
from backend.curve_service import CurveController
from backend.fan_service import FanService
from backend.profile_service import ProfileService
from hardware.mock_backend import MockFanBackend


class FixedTemperature:
    def get_cpu_temperature(self):
        return 67.0


def build_client(tmp_path, *, writes_allowed=True):
    backend = MockFanBackend()
    service = FanService(
        backend,
        model="ASUS BR1402FGA" if writes_allowed else "Unknown laptop",
        writes_allowed=writes_allowed,
        mock_mode=writes_allowed,
    )
    database = Database(tmp_path / "app.db")
    temperature = FixedTemperature()
    controller = CurveController(service, temperature, lambda: 60.0)
    profiles = ProfileService(database, service, controller)
    app = create_app(
        service, database, temperature, "frontend", controller, profiles
    )
    app.testing = True
    return app.test_client(), app.config["APP_TOKEN"], backend, controller


def test_status_contains_live_values(tmp_path):
    client, _, _, _ = build_client(tmp_path)
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json["cpu_temperature"] == 67.0
    assert response.json["fan_count"] == 1
    assert response.json["ec"] == {"status": 0, "obf": False, "ibf": False}
    assert response.json["fans"][0]["rpm"] == 3800
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert "style-src 'self' 'unsafe-inline'" in response.headers["Content-Security-Policy"]
    assert "script-src 'self';" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"


def test_manual_requires_token_and_strict_json(tmp_path):
    client, token, backend, _ = build_client(tmp_path)
    assert client.post("/api/fans/0/manual", json={"percent": 60}).status_code == 403
    response = client.post(
        "/api/fans/0/manual",
        json={"percent": 60, "raw": "82 35 ff"},
        headers={"X-App-Token": token},
    )
    assert response.status_code == 400
    assert backend.test_modes[0] is False

    response = client.post(
        "/api/fans/0/manual",
        json={"percent": 80},
        headers={"X-App-Token": token},
    )
    assert response.status_code == 200
    assert response.json["mode"] == "manual"


def test_api_validates_percent_and_fan_index(tmp_path):
    client, token, _, _ = build_client(tmp_path)
    headers = {"X-App-Token": token}
    assert client.post("/api/fans/0/manual", json={"percent": 0}, headers=headers).status_code == 400
    assert client.post("/api/fans/0/manual", json={"percent": True}, headers=headers).status_code == 400
    assert client.post("/api/fans/4/manual", json={"percent": 60}, headers=headers).status_code == 400


def test_unknown_hardware_write_is_forbidden(tmp_path):
    client, token, backend, _ = build_client(tmp_path, writes_allowed=False)
    response = client.post(
        "/api/fans/0/manual", json={"percent": 60}, headers={"X-App-Token": token}
    )
    assert response.status_code == 403
    assert backend.operations == []


def test_settings_api(tmp_path):
    client, token, _, _ = build_client(tmp_path)
    response = client.put(
        "/api/settings",
        json={"poll_interval_ms": 3000},
        headers={"X-App-Token": token},
    )
    assert response.status_code == 200
    assert response.json["settings"]["poll_interval_ms"] == 3000


def test_curve_api_starts_and_restores_owned_control(tmp_path):
    client, token, backend, controller = build_client(tmp_path)
    response = client.post(
        "/api/curve/start",
        json={
            "fan": 0,
            "name": "Test curve",
            "points": [
                {"temperature": 40, "percent": 30},
                {"temperature": 80, "percent": 90},
            ],
        },
        headers={"X-App-Token": token},
    )
    assert response.status_code == 200
    assert response.json["controller"]["active"] is True
    assert response.json["controller"]["target_percent"] == 70
    assert backend.test_modes[0] is True

    response = client.post(
        "/api/curve/stop", headers={"X-App-Token": token}
    )
    assert response.status_code == 200
    assert controller.status()["active"] is False
    assert backend.test_modes[0] is False


def test_direct_restore_stops_curve_before_restoring(tmp_path):
    client, token, backend, controller = build_client(tmp_path)
    headers = {"X-App-Token": token}
    client.post(
        "/api/curve/start",
        json={
            "points": [
                {"temperature": 40, "percent": 30},
                {"temperature": 80, "percent": 90},
            ]
        },
        headers=headers,
    )
    response = client.post("/api/fans/0/restore", headers=headers)
    assert response.status_code == 200
    assert controller.status()["active"] is False
    assert backend.test_modes[0] is False


def test_profile_api_create_apply_and_delete(tmp_path):
    client, token, backend, _ = build_client(tmp_path)
    headers = {"X-App-Token": token}
    created = client.post(
        "/api/profiles",
        json={"name": "Gaming", "mode": "manual", "percent": 85},
        headers=headers,
    )
    assert created.status_code == 201
    profile_id = created.json["profile"]["id"]

    applied = client.post(
        f"/api/profiles/{profile_id}/apply", json={"fan": 0}, headers=headers
    )
    assert applied.status_code == 200
    assert backend.percents[0] == 85
    assert client.delete(f"/api/profiles/{profile_id}", headers=headers).status_code == 409

    client.post("/api/fans/0/restore", headers=headers)
    assert client.delete(f"/api/profiles/{profile_id}", headers=headers).status_code == 200


def test_curve_and_profile_endpoints_reject_unsupported_fields(tmp_path):
    client, token, _, _ = build_client(tmp_path)
    headers = {"X-App-Token": token}
    assert client.post(
        "/api/curve/start",
        json={"points": [], "raw_command": "DD"},
        headers=headers,
    ).status_code == 400
    assert client.post(
        "/api/profiles",
        json={"name": "Unsafe", "mode": "manual", "percent": 50, "port": 0x25C},
        headers=headers,
    ).status_code == 400
