#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import ctypes
import os
import platform
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from werkzeug.serving import BaseWSGIServer, make_server

from backend.api import create_app
from backend.config import AppConfig, is_supported_model, read_system_model
from backend.curve_service import CurveController, CurveError
from backend.database import Database
from backend.fan_service import FanService
from backend.instance_lock import ApplicationAlreadyRunning, ApplicationLock
from backend.profile_service import ProfileService
from backend.temperature_service import TemperatureService, WindowsAsusTemperatureService
from hardware.helper_client import NativeHelperBackend, WindowsAsusBackend
from hardware.mock_backend import MockFanBackend

PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def unblock_bundled_files(root: Path) -> None:
    """Strip the NTFS "Zone.Identifier" stream Windows attaches to files
    extracted from a downloaded ZIP. With that mark still set, .NET Framework
    refuses to load pythonnet's Python.Runtime.dll from the bundle, which
    surfaces as "Failed to resolve Python.Runtime.Loader.Initialize" when
    pywebview's edgechromium backend imports clr. This mirrors right-clicking
    the file and choosing "Unblock"."""
    for path in root.rglob("*"):
        if path.is_file():
            try:
                os.remove(f"{path}:Zone.Identifier")
            except OSError:
                pass


def process_is_elevated() -> bool:
    if platform.system() == "Windows":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


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
    if process_is_elevated():
        print("Refusing to run the Flask/GUI process with administrator privileges.", file=sys.stderr)
        return 2
    if not 0 <= args.port <= 65535:
        print("Port must be between 0 and 65535.", file=sys.stderr)
        return 2

    model = args.model or ("Mock ASUS BR1402FGA" if args.mock else read_system_model())
    if args.mock:
        hardware = MockFanBackend()
        writes_allowed = True
    elif platform.system() == "Windows":
        hardware = WindowsAsusBackend(args.helper)
        writes_allowed = is_supported_model(model) and platform.machine().upper() in {
            "AMD64",
            "X86_64",
        }
    else:
        hardware = NativeHelperBackend(args.helper, use_sudo=not args.no_sudo)
        writes_allowed = is_supported_model(model)

    database = Database(args.database)
    instance_lock = ApplicationLock(args.database.with_suffix(".lock"))
    try:
        instance_lock.acquire()
    except ApplicationAlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        return 2
    service = FanService(
        hardware,
        model=model,
        writes_allowed=writes_allowed,
        mock_mode=args.mock,
    )
    temperature_service = (
        WindowsAsusTemperatureService(hardware)
        if platform.system() == "Windows" and not args.mock
        else TemperatureService()
    )
    curve_controller = CurveController(
        service,
        temperature_service,
        lambda: database.get_settings()["poll_interval_ms"] / 1000.0,
    )
    profile_service = ProfileService(database, service, curve_controller)
    flask_app = create_app(
        service,
        database,
        temperature_service,
        PROJECT_ROOT / "frontend",
        curve_controller,
        profile_service,
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
            try:
                curve_controller.stop(restore=True)
            except CurveError as exc:
                print(f"Warning: failed to stop curve controller: {exc.message}", file=sys.stderr)
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
            instance_lock.release()

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

    if platform.system() == "Windows":
        unblock_bundled_files(PROJECT_ROOT)

    try:
        import webview
        from webview.errors import WebViewException
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
        min_size=(800, 600),
    )

    def close_on_signal() -> None:
        stop_event.wait()
        try:
            window.destroy()
        except Exception:
            pass

    threading.Thread(target=close_on_signal, name="signal-window-close", daemon=True).start()
    try:
        # The project installs pywebview's PySide6 extra. Selecting Qt explicitly
        # avoids a noisy GTK probe and keeps the isolated virtualenv self-contained.
        webview.start(
            gui="edgechromium" if platform.system() == "Windows" else "qt",
            debug=False,
        )
    except WebViewException as exc:
        print(
            f"Unable to start the desktop window: {exc}\n"
            "Run 'make setup' to install the Qt backend, or use '--no-gui'.",
            file=sys.stderr,
        )
        return 2
    finally:
        cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
