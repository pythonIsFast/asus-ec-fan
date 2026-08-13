from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from .database import Database
from .fan_service import FanService, FanServiceError
from .temperature_service import TemperatureService


def create_app(
    fan_service: FanService,
    database: Database,
    temperature_service: TemperatureService,
    frontend_dir: str | Path,
) -> Flask:
    frontend = Path(frontend_dir)
    app = Flask(
        __name__,
        template_folder=str(frontend),
        static_folder=str(frontend),
        static_url_path="/assets",
    )
    app.config.update(JSON_SORT_KEYS=False, APP_TOKEN=secrets.token_urlsafe(32))
    last_telemetry: dict[int, float] = {}

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def error_response(code: str, message: str, status: int):
        return jsonify(ok=False, error=code, message=message), status

    def require_app_token():
        supplied = request.headers.get("X-App-Token", "")
        if not secrets.compare_digest(supplied, app.config["APP_TOKEN"]):
            return error_response("INVALID_APP_TOKEN", "Missing or invalid app token", 403)
        return None

    @app.errorhandler(FanServiceError)
    def handle_service_error(exc: FanServiceError):
        return error_response(exc.code, exc.message, exc.status_code)

    @app.get("/")
    def index():
        return render_template("index.html", app_token=app.config["APP_TOKEN"])

    @app.get("/api/status")
    def status():
        temperature = temperature_service.get_cpu_temperature()
        payload: dict[str, Any] = {
            "ok": True,
            "device": fan_service.device_status(),
            "cpu_temperature": temperature,
        }
        try:
            payload["ec"] = fan_service.get_ec_status()
            fans = fan_service.get_fans()
            payload["fans"] = fans
            payload["fan_count"] = len(fans)
            settings = database.get_settings()
            if settings["telemetry_enabled"]:
                now = time.monotonic()
                interval = max(10.0, settings["poll_interval_ms"] / 1000.0)
                for fan in fans:
                    if now - last_telemetry.get(fan["id"], 0.0) >= interval:
                        database.add_telemetry(
                            fan["id"], fan["rpm"], fan["mode"], temperature
                        )
                        last_telemetry[fan["id"]] = now
        except FanServiceError as exc:
            payload.update(
                hardware_error={"error": exc.code, "message": exc.message},
                fans=[],
                fan_count=0,
            )
        return jsonify(payload)

    @app.get("/api/fans")
    def fans():
        return jsonify(ok=True, fans=fan_service.get_fans())

    @app.get("/api/fans/<int:fan_index>")
    def fan(fan_index: int):
        return jsonify(ok=True, fan=fan_service.get_fan(fan_index))

    @app.post("/api/fans/<int:fan_index>/manual")
    def manual(fan_index: int):
        token_error = require_app_token()
        if token_error:
            return token_error
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {"percent"}:
            return error_response(
                "INVALID_REQUEST", "Expected JSON containing only percent", 400
            )
        return jsonify(fan_service.set_manual(fan_index, payload["percent"]))

    @app.post("/api/fans/<int:fan_index>/restore")
    def restore(fan_index: int):
        token_error = require_app_token()
        if token_error:
            return token_error
        if request.content_length and request.content_length > 0:
            payload = request.get_json(silent=True)
            if payload not in ({}, None):
                return error_response("INVALID_REQUEST", "Restore takes no fields", 400)
        return jsonify(fan_service.restore(fan_index))

    @app.get("/api/settings")
    def get_settings():
        return jsonify(ok=True, settings=database.get_settings())

    @app.put("/api/settings")
    def put_settings():
        token_error = require_app_token()
        if token_error:
            return token_error
        try:
            settings = database.update_settings(request.get_json(silent=True))
        except ValueError as exc:
            return error_response("INVALID_SETTINGS", str(exc), 400)
        return jsonify(ok=True, settings=settings)

    @app.get("/api/history")
    def history():
        try:
            limit = int(request.args.get("limit", "250"))
        except ValueError:
            return error_response("INVALID_LIMIT", "limit must be an integer", 400)
        return jsonify(ok=True, history=database.get_history(limit))

    return app
