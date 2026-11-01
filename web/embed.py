"""Run the web server inside the desktop app: uvicorn on a background thread,
its Qt drawing done by a timer on the app's own main thread. The app calls
start() when it opens (File > Web access) and stop() when it closes."""

from __future__ import annotations

import socket
import threading
import time


def lan_address() -> str:
    """This PC's address on the network (what other PCs type), or localhost."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))  # picks the outgoing interface; nothing is sent
            ip = s.getsockname()[0]
        finally:
            s.close()
        if not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return "localhost"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


class WebShare:
    """The web pages, served from the desktop app. status: "running", "busy"
    (the port is taken, usually by another window or start_web.bat), "error"
    (message in .error) or "stopped"."""

    def __init__(self, cfg: dict | None = None, extra_folders=None):
        self.cfg, self.extra_folders = cfg, extra_folders
        self.server = self.thread = self.timer = None
        self.status, self.error, self.url = "stopped", "", ""

    def start(self) -> str:
        try:
            import uvicorn
            from web import core
            from web.server import create_app
        except ImportError as e:  # fastapi / uvicorn not installed
            self.status = "error"
            self.error = (f"needs {e.name or 'fastapi'}: py -3.13 -m pip install -r web\\requirements.txt")
            return self.status
        from PySide6.QtCore import QTimer
        cfg = dict(self.cfg or core.load_config())
        port = int(cfg["port"])
        self.url = f"http://{lan_address() if cfg.get('host', '0.0.0.0') != '127.0.0.1' else 'localhost'}:{port}"
        if port_in_use(port):
            self.status = "busy"
            return self.status
        if self.extra_folders is not None:
            cfg["extra_folders"] = self.extra_folders
        app = create_app(cfg)
        self.server = uvicorn.Server(uvicorn.Config(app, host=cfg.get("host", "0.0.0.0"), port=port,
                                                    log_level="warning", timeout_graceful_shutdown=2))
        box = {}

        def run():
            try:
                self.server.run()
            except BaseException as e:  # noqa: BLE001 - e.g. SystemExit when the port can't be bound
                box["error"] = e

        self.timer = QTimer()  # the web's Qt drawing runs here, on the app's main thread
        self.timer.timeout.connect(core.serve_jobs)
        self.timer.start(15)
        core.set_qt_served(True)
        self.thread = threading.Thread(target=run, name="web-server", daemon=True)
        self.thread.start()
        t0 = time.time()
        while not self.server.started and self.thread.is_alive() and time.time() - t0 < 10:
            time.sleep(0.05)
        if not self.server.started:
            self.stop()
            self.status = "busy" if port_in_use(port) else "error"
            self.error = self.error or f"could not start on port {port} ({box.get('error')!r})"
            return self.status
        self.status = "running"
        return self.status

    def stop(self) -> None:
        if self.server is None:
            self.status = "stopped" if self.status == "running" else self.status
            return
        from web import core
        self.server.should_exit = True
        t0 = time.time()
        while self.thread.is_alive() and time.time() - t0 < 5:
            core.serve_jobs()  # a request may be waiting for a drawing: let it finish
            self.thread.join(0.05)
        core.set_qt_served(False)
        core.serve_jobs()
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        self.server = self.thread = None
        self.status = "stopped"
