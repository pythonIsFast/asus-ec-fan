from __future__ import annotations

import sqlite3
import threading
from typing import Any

from hardware.protocol import validate_percent

from .curve_service import CurveController, CurveError, validate_curve_points
from .database import Database
from .fan_service import FanService, FanServiceError


class ProfileError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ProfileService:
    def __init__(
        self, database: Database, fan_service: FanService, curve_controller: CurveController
    ) -> None:
        self._database = database
        self._fan_service = fan_service
        self._curve_controller = curve_controller
        self._lock = threading.Lock()
        self._active_profile_id: int | None = None

    @staticmethod
    def _validate_payload(payload: object) -> tuple[str, str, int | None, list[dict[str, int]] | None]:
        if not isinstance(payload, dict):
            raise ProfileError("INVALID_PROFILE", "Profile must be a JSON object")
        allowed = {"name", "mode", "percent", "curve_points"}
        if set(payload) - allowed:
            raise ProfileError("INVALID_PROFILE", "Profile contains unsupported fields")
        name = payload.get("name")
        mode = payload.get("mode")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            raise ProfileError("INVALID_PROFILE", "Profile name must be 1–60 characters")
        if mode not in {"firmware", "manual", "curve"}:
            raise ProfileError("INVALID_PROFILE", "Profile mode is invalid")
        percent: int | None = None
        curve_points: list[dict[str, int]] | None = None
        if mode == "manual":
            try:
                percent = validate_percent(payload.get("percent"))
            except ValueError as exc:
                raise ProfileError("INVALID_PROFILE", str(exc)) from exc
        elif mode == "curve":
            points = validate_curve_points(payload.get("curve_points"))
            curve_points = [point.as_dict() for point in points]
        return name.strip(), mode, percent, curve_points

    def list_profiles(self) -> dict[str, Any]:
        with self._lock:
            active = (
                self._database.get_profile(self._active_profile_id)
                if self._active_profile_id
                else None
            )
            if (
                active
                and active["mode"] == "curve"
                and not self._curve_controller.status()["active"]
            ):
                self._active_profile_id = None
        return {
            "profiles": self._database.get_profiles(),
            "active_profile_id": self._active_profile_id,
        }

    def create(self, payload: object) -> dict[str, Any]:
        name, mode, percent, curve_points = self._validate_payload(payload)
        try:
            return self._database.create_profile(name, mode, percent, curve_points)
        except sqlite3.IntegrityError as exc:
            raise ProfileError("PROFILE_EXISTS", "A profile with this name already exists") from exc

    def delete(self, profile_id: int) -> None:
        with self._lock:
            if profile_id == self._active_profile_id:
                raise ProfileError("PROFILE_ACTIVE", "Stop or change the active profile first", 409)
            profile = self._database.get_profile(profile_id)
            if profile is None:
                raise ProfileError("PROFILE_NOT_FOUND", "Profile not found", 404)
            if profile["built_in"]:
                raise ProfileError("PROFILE_BUILT_IN", "Built-in profiles cannot be deleted", 403)
            if not self._database.delete_profile(profile_id):
                raise ProfileError("PROFILE_NOT_FOUND", "Profile not found", 404)

    def apply(self, profile_id: int, fan: int = 0) -> dict[str, Any]:
        profile = self._database.get_profile(profile_id)
        if profile is None:
            raise ProfileError("PROFILE_NOT_FOUND", "Profile not found", 404)
        try:
            if profile["mode"] == "firmware":
                self._curve_controller.stop(restore=False)
                result = self._fan_service.restore(fan)
            elif profile["mode"] == "manual":
                self._curve_controller.stop(restore=False)
                result = self._fan_service.set_manual(fan, profile["percent"])
            else:
                result = self._curve_controller.start(
                    fan, profile["curve_points"], profile["name"]
                )
        except (FanServiceError, CurveError) as exc:
            raise ProfileError(exc.code, exc.message, exc.status_code) from exc
        with self._lock:
            self._active_profile_id = profile_id
        return {"ok": True, "profile": profile, "result": result}

    def clear_active_curve(self) -> None:
        with self._lock:
            active = self._database.get_profile(self._active_profile_id) if self._active_profile_id else None
            if active and active["mode"] == "curve":
                self._active_profile_id = None

    def clear_active(self) -> None:
        with self._lock:
            self._active_profile_id = None
