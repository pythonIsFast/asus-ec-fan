from backend.api import create_app
from backend.database import Database
from backend.fan_service import FanService
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
    app = create_app(service, Database(tmp_path / "app.db"), FixedTemperature(), "frontend")
    app.testing = True
    return app.test_client(), app.config["APP_TOKEN"], backend


def test_status_contains_live_values(tmp_path):
    client, _, _ = build_client(tmp_path)
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json["cpu_temperature"] == 67.0
    assert response.json["fan_count"] == 1
    assert response.json["ec"] == {"status": 0, "obf": False, "ibf": False}
    assert response.json["fans"][0]["rpm"] == 3800
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"


def test_manual_requires_token_and_strict_json(tmp_path):
    client, token, backend = build_client(tmp_path)
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
    client, token, _ = build_client(tmp_path)
    headers = {"X-App-Token": token}
    assert client.post("/api/fans/0/manual", json={"percent": 0}, headers=headers).status_code == 400
    assert client.post("/api/fans/0/manual", json={"percent": True}, headers=headers).status_code == 400
    assert client.post("/api/fans/4/manual", json={"percent": 60}, headers=headers).status_code == 400


def test_unknown_hardware_write_is_forbidden(tmp_path):
    client, token, backend = build_client(tmp_path, writes_allowed=False)
    response = client.post(
        "/api/fans/0/manual", json={"percent": 60}, headers={"X-App-Token": token}
    )
    assert response.status_code == 403
    assert backend.operations == []


def test_settings_api(tmp_path):
    client, token, _ = build_client(tmp_path)
    response = client.put(
        "/api/settings",
        json={"poll_interval_ms": 3000},
        headers={"X-App-Token": token},
    )
    assert response.status_code == 200
    assert response.json["settings"]["poll_interval_ms"] == 3000
