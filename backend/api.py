from __future__ import annotations

import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from .database import Database
from .curve_service import CurveController, CurveError
from .fan_service import FanService, FanServiceError
from .profile_service import ProfileError, ProfileService
from .temperature_service import TemperatureReader


def create_app(
    fan_service: FanService,
    database: Database,
    temperature_service: TemperatureReader,
    frontend_dir: str | Path,
    curve_controller: CurveController,
    profile_service: ProfileService,
) -> Flask:
    frontend = Path(frontend_dir)
    app = Flask(
        __name__,
        template_folder=str(frontend),
        static_folder=str(frontend),
        static_url_path="/assets",
    )
    app.config.update(
        JSON_SORT_KEYS=False,
        APP_TOKEN=secrets.token_urlsafe(32),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    last_telemetry: dict[int, float] = {}

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def error_response(code: str, message: str, status: int):
        return jsonify(ok=False, error=code, message=message), status

    def record_event(event_type: str, details: dict[str, Any]) -> None:
        try:
            database.add_event(event_type, details)
        except (OSError, sqlite3.Error):
            app.logger.warning("Unable to persist event %s", event_type, exc_info=True)

    def require_app_token():
        supplied = request.headers.get("X-App-Token", "")
        if not secrets.compare_digest(supplied, app.config["APP_TOKEN"]):
            return error_response("INVALID_APP_TOKEN", "Missing or invalid app token", 403)
        return None

    @app.errorhandler(FanServiceError)
    def handle_service_error(exc: FanServiceError):
        return error_response(exc.code, exc.message, exc.status_code)

    @app.errorhandler(CurveError)
    @app.errorhandler(ProfileError)
    def handle_control_error(exc):
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
            "curve_controller": curve_controller.status(),
            "profiles": profile_service.list_profiles(),
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
        try:
            curve_controller.stop(restore=False)
            profile_service.clear_active()
            result = fan_service.set_manual(fan_index, payload["percent"])
        except FanServiceError as exc:
            record_event(
                "manual_failed",
                {"fan": fan_index, "error": exc.code, "message": exc.message},
            )
            raise
        record_event(
            "manual_applied", {"fan": fan_index, "percent": result["percent"]}
        )
        return jsonify(result)

    @app.post("/api/fans/<int:fan_index>/restore")
    def restore(fan_index: int):
        token_error = require_app_token()
        if token_error:
            return token_error
        if request.content_length and request.content_length > 0:
            payload = request.get_json(silent=True)
            if payload not in ({}, None):
                return error_response("INVALID_REQUEST", "Restore takes no fields", 400)
        try:
            curve_controller.stop(restore=False)
            profile_service.clear_active()
            result = fan_service.restore(fan_index)
        except FanServiceError as exc:
            record_event(
                "restore_failed",
                {"fan": fan_index, "error": exc.code, "message": exc.message},
            )
            raise
        record_event("firmware_restored", {"fan": fan_index})
        return jsonify(result)

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

    @app.get("/api/curve")
    def curve_status():
        return jsonify(ok=True, controller=curve_controller.status())

    @app.post("/api/curve/start")
    def curve_start():
        token_error = require_app_token()
        if token_error:
            return token_error
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) - {"fan", "name", "points"}:
            return error_response(
                "INVALID_REQUEST", "Expected fan, name, and curve points", 400
            )
        profile_service.clear_active()
        controller = curve_controller.start(
            payload.get("fan", 0), payload.get("points"), payload.get("name", "Custom curve")
        )
        record_event("curve_started", {"fan": controller["fan"], "name": controller["name"]})
        return jsonify(ok=True, controller=controller)

    @app.post("/api/curve/stop")
    def curve_stop():
        token_error = require_app_token()
        if token_error:
            return token_error
        payload = request.get_json(silent=True)
        if payload not in (None, {}) and payload != {"restore": True}:
            return error_response("INVALID_REQUEST", "Curve stop accepts only restore=true", 400)
        controller = curve_controller.stop(restore=True)
        profile_service.clear_active_curve()
        record_event("curve_stopped", {"fan": controller["fan"]})
        return jsonify(ok=True, controller=controller)

    @app.get("/api/profiles")
    def profiles():
        return jsonify(ok=True, **profile_service.list_profiles())

    @app.post("/api/profiles")
    def create_profile():
        token_error = require_app_token()
        if token_error:
            return token_error
        profile = profile_service.create(request.get_json(silent=True))
        record_event("profile_created", {"profile_id": profile["id"], "name": profile["name"]})
        return jsonify(ok=True, profile=profile), 201

    @app.delete("/api/profiles/<int:profile_id>")
    def delete_profile(profile_id: int):
        token_error = require_app_token()
        if token_error:
            return token_error
        profile_service.delete(profile_id)
        record_event("profile_deleted", {"profile_id": profile_id})
        return jsonify(ok=True)

    @app.post("/api/profiles/<int:profile_id>/apply")
    def apply_profile(profile_id: int):
        token_error = require_app_token()
        if token_error:
            return token_error
        payload = request.get_json(silent=True)
        if payload not in (None, {}) and (
            not isinstance(payload, dict) or set(payload) != {"fan"}
        ):
            return error_response("INVALID_REQUEST", "Expected optional fan only", 400)
        fan = payload.get("fan", 0) if isinstance(payload, dict) else 0
        result = profile_service.apply(profile_id, fan)
        record_event(
            "profile_applied",
            {"profile_id": profile_id, "name": result["profile"]["name"]},
        )
        return jsonify(result)

    return app
