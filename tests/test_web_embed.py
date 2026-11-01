"""The web pages served from inside the desktop app (File > Web access)."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.app import MainWindow  # noqa: E402
from web.embed import port_in_use  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(app, url):
    """Fetch while the app's main thread keeps serving (the web's Qt drawing runs there)."""
    box = {}

    def go():
        try:
            box["r"] = urllib.request.urlopen(url, timeout=60).read()
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    t = threading.Thread(target=go)
    t.start()
    while t.is_alive():
        app.processEvents()
        t.join(0.02)
    if "e" in box:
        raise box["e"]
    return box["r"]


def _window(port):
    app = QApplication.instance() or QApplication([])
    d = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "examples" / "small_board.json", d / "small_board.json")  # a copy: the real file is never touched
    w = MainWindow(str(d / "small_board.json"))
    assert w.web is None  # no auto-start on a headless (test) display
    w.web_config = {"folders": [d], "password": "", "host": "127.0.0.1", "port": port}
    return app, w, d


def test_start_stop_with_the_app():
    port = _free_port()
    app, w, d = _window(port)
    w.set_web(True, remember=False)
    assert w.web.status == "running" and port_in_use(port)
    assert f"http://localhost:{port}" in w.web_lbl.text() and "#2e9e44" in w.web_dot.styleSheet()  # green dot
    assert w.menuBar().cornerWidget() is w.web_lbl.parent()  # in the menu bar, not the status bar
    lays = json.loads(_get(app, f"http://127.0.0.1:{port}/api/layouts"))["layouts"]
    assert [x["name"] for x in lays] == ["small_board.json"]
    info = json.loads(_get(app, f"http://127.0.0.1:{port}/api/layout/0/small_board.json"))  # Qt drawing work
    assert "points" in info
    assert b"<svg" in _get(app, f"http://127.0.0.1:{port}/api/layout/0/small_board.json/2d.svg")[:3000]
    w.set_web(False, remember=False)
    assert not port_in_use(port) and w.web_lbl.text() == "Web: off"
    w.set_web(True, remember=False)
    assert port_in_use(port)
    w.scene.undo.setClean()
    assert w.close()  # closing the app stops the server
    assert not port_in_use(port)


def test_port_busy():
    port = _free_port()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)
    try:
        _app, w, _d = _window(port)
        w.set_web(True, remember=False)  # another window or start_web.bat already serves it: no crash
        assert w.web.status == "busy" and "already running" in w.web_lbl.text()
        w.scene.undo.setClean()
        assert w.close()
    finally:
        blocker.close()


def test_missing_dependency():
    port = _free_port()
    _app, w, _d = _window(port)
    with mock.patch.dict(sys.modules, {"uvicorn": None}):  # as if uvicorn weren't installed
        w.set_web(True, remember=False)
    assert w.web.status == "error" and w.web_lbl.text() == "Web: unavailable"
    assert "pip install" in w.web_lbl.toolTip() and not port_in_use(port)
    w.add_point_on(next(iter(w.scene.layout.beams)))  # the app itself carries on as normal
    w.scene.undo.setClean()
    assert w.close()


if __name__ == "__main__":
    test_start_stop_with_the_app()
    test_port_busy()
    test_missing_dependency()
    print("ok")
