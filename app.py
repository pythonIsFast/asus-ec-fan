#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from werkzeug.serving import BaseWSGIServer, make_server

from backend.api import create_app
from backend.config import AppConfig, is_supported_model, read_system_model
from backend.database import Database
from backend.fan_service import FanService
from backend.temperature_service import TemperatureService
from hardware.helper_client import NativeHelperBackend
from hardware.mock_backend import MockFanBackend

PROJECT_ROOT = Path(__file__).resolve().parent


class LocalServer:
    def __init__(self, flask_app: Any, host: str, port: int) -> None:
        if host != "127.0.0.1":
            raise ValueError("The application server may bind only to 127.0.0.1")
        self._server: BaseWSGIServer = make_server(host, port, flask_app, threaded=True)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="flask-localhost", daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=3)


def parse_args() -> argparse.Namespace:
    defaults = AppConfig.defaults(PROJECT_ROOT)
    parser = argparse.ArgumentParser(description="ASUS EC Fan desktop controller")
    parser.add_argument("--mock", action="store_true", help="use safe simulated hardware")
    parser.add_argument("--no-gui", action="store_true", help="serve the UI without pywebview")
    parser.add_argument("--no-sudo", action="store_true", help="invoke helper directly")
    parser.add_argument("--port", type=int, default=0, help="localhost port (0 chooses one)")
    parser.add_argument("--helper", type=Path, default=defaults.helper_path)
    parser.add_argument("--database", type=Path, default=defaults.database_path)
    parser.add_argument("--model", help="DMI model override for development")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.geteuid() == 0:
        print("Refusing to run the Flask/GUI process as root.", file=sys.stderr)
        return 2
    if not 0 <= args.port <= 65535:
        print("Port must be between 0 and 65535.", file=sys.stderr)
        return 2

    model = args.model or ("Mock ASUS BR1402FGA" if args.mock else read_system_model())
    if args.mock:
        hardware = MockFanBackend()
        writes_allowed = True
    else:
        hardware = NativeHelperBackend(args.helper, use_sudo=not args.no_sudo)
        writes_allowed = is_supported_model(model)

    database = Database(args.database)
    service = FanService(
        hardware,
        model=model,
        writes_allowed=writes_allowed,
        mock_mode=args.mock,
    )
    flask_app = create_app(
        service, database, TemperatureService(), PROJECT_ROOT / "frontend"
    )
    server = LocalServer(flask_app, "127.0.0.1", args.port)
    cleanup_lock = threading.Lock()
    cleaned_up = False

    def cleanup() -> None:
        nonlocal cleaned_up
        with cleanup_lock:
            if cleaned_up:
                return
            cleaned_up = True
            failures = service.restore_session_owned()
            if failures:
                for failure in failures:
                    print(
                        f"Warning: failed to restore fan {failure['fan']}: "
                        f"{failure['message']}",
                        file=sys.stderr,
                    )
            try:
                server.stop()
            except (RuntimeError, OSError):
                pass

    atexit.register(cleanup)
    server.start()

    stop_event = threading.Event()

    def signal_handler(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.no_gui:
        print(f"ASUS EC Fan is available at {server.url}")
        try:
            while not stop_event.wait(0.25):
                pass
        finally:
            cleanup()
        return 0

    try:
        import webview
    except ImportError:
        cleanup()
        print("pywebview is not installed. Run 'make setup' or use --no-gui.", file=sys.stderr)
        return 2

    settings = database.get_settings()
    window = webview.create_window(
        "ASUS EC Fan",
        server.url,
        width=settings["window_width"],
        height=settings["window_height"],
        min_size=(520, 560),
    )

    def close_on_signal() -> None:
        stop_event.wait()
        try:
            window.destroy()
        except Exception:
            pass

    threading.Thread(target=close_on_signal, name="signal-window-close", daemon=True).start()
    try:
        webview.start(debug=False)
    finally:
        cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
