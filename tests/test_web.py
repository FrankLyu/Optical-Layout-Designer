"""Web viewer and power logger (web/): login, layouts read-only, logging on a copy."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from optolayout.logbook import Logbook  # noqa: E402
from web import core  # noqa: E402
from web.server import create_app  # noqa: E402

EX = ROOT / "examples"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201c5a1a8"
                    "a50000000049454e44ae426082")


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _setup():
    d = Path(tempfile.mkdtemp())
    for f in ("demo_399nm.json", "demo_399nm.logbook.sqlite", "small_board.json"):
        shutil.copy(EX / f, d / f)
    (d / "notes.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    app = create_app({"folders": [d], "password": "secret", "host": "127.0.0.1", "port": 8000})
    return d, TestClient(app)


def _login(c):
    r = c.post("/login", data={"password": "secret", "next": "/"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_password():
    core.with_qt_loop(_test_password)


def _test_password():
    _d, c = _setup()
    assert c.get("/api/layouts").status_code == 401
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert c.get("/static/style.css").status_code == 200  # the login page needs its style
    r = c.post("/login", data={"password": "wrong"}, follow_redirects=False)
    assert "bad=1" in r.headers["location"] and c.get("/api/layouts").status_code == 401
    r = c.post("/login", data={"password": "secret", "next": "//evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"  # no redirect off the site
    assert c.get("/api/layouts").status_code == 200 and c.get("/").status_code == 200
    c.get("/logout")
    c.cookies.clear()
    assert c.get("/api/layouts").status_code == 401


def test_layouts_read_only():
    core.with_qt_loop(_test_layouts_read_only)


def _test_layouts_read_only():
    d, c = _setup()
    _login(c)
    lay, log = d / "demo_399nm.json", d / "demo_399nm.logbook.sqlite"
    before = (_digest(lay), _digest(log))
    names = [x["name"] for x in c.get("/api/layouts").json()["layouts"]]
    assert names == ["demo_399nm.json", "small_board.json"]  # notes.json is not a layout
    base = "/api/layout/0/demo_399nm.json"
    info = c.get(base).json()
    assert info["title"] and len(info["points"]) == 5 and info["has_log"]
    p0 = next(p for p in info["points"] if p["power"])
    assert p0["when"] and "change_pct" in p0 and "name" in p0
    d2 = c.get(base + "/2d").json()
    assert d2["width"] > 100 and len(d2["points"]) == 5 and len(d2["points"][0]["box"]) == 4
    svg = c.get(base + "/2d.svg")
    assert svg.headers["content-type"].startswith("image/svg") and b"<svg" in svg.content[:2000]
    assert c.get(base + "/picture.png?w=400").content[:4] == b"\x89PNG"
    assert c.get(base + "/3d.json").status_code == 404  # no 3D on the web: only in the desktop app
    sheet = c.get("/layout/0/demo_399nm.json/sheet?points=" + p0["id"] + "&pic=0")
    assert sheet.status_code == 200 and "<table" in sheet.text and p0["label"] in sheet.text
    pl = c.get(f"{base}/point/{p0['id']}").json()
    assert pl["history"] and pl["desc"] and "mW" in pl["units"]
    for page in ("/", "/layout/0/demo_399nm.json", f"/layout/0/demo_399nm.json/point/{p0['id']}"):
        assert c.get(page).status_code == 200
    # viewing never writes: not the layout, not the log
    assert (_digest(lay), _digest(log)) == before
    # only listed layouts can be reached
    for bad in ("/api/layout/0/notes.json", "/api/layout/5/demo_399nm.json", "/api/layout/0/..%2Fx.json",
                f"{base}/point/nope"):
        assert c.get(bad).status_code == 404, bad


def test_logging_on_a_copy():
    core.with_qt_loop(_test_logging_on_a_copy)


def _test_logging_on_a_copy():
    d, c = _setup()
    _login(c)
    lay, log = d / "demo_399nm.json", d / "demo_399nm.logbook.sqlite"
    lay_before = _digest(lay)
    base = "/api/layout/0/demo_399nm.json"
    pid = c.get(base).json()["points"][0]["id"]
    desk = Logbook(log)  # the desktop app, open at the same time
    assert not desk.changed_on_disk()
    r = c.post(f"{base}/point/{pid}/reading", data={"value": "12.5", "unit": "µW", "meter": "S121C", "notes": "web"})
    assert r.status_code == 200
    assert desk.changed_on_disk() and not desk.changed_on_disk()  # the desktop notices, once
    rec = desk.power_history(pid)[-1]
    assert rec.id == r.json()["id"] and abs(rec.power_mw - 0.0125) < 1e-12 and rec.unit == "µW"
    assert (rec.instrument, rec.notes, rec.supersedes) == ("S121C", "web", None) and len(rec.measured_at) == 19
    assert pid in dict(desk.known_points())
    pl = c.get(f"{base}/point/{pid}").json()
    assert pl["history"][-1]["power"] == "12.5 µW" and pl["power"] == "12.5 µW"
    assert c.post(f"{base}/point/{pid}/reading", data={"value": "0"}).status_code == 400
    assert c.post(f"{base}/point/{pid}/reading", data={"value": "1", "unit": "kW"}).status_code == 400
    assert c.post(f"{base}/point/nope/reading", data={"value": "1"}).status_code == 404
    # a beam picture, from a file or the phone's camera
    r = c.post(f"{base}/point/{pid}/picture", files={"file": ("beam.png", PNG, "image/png")}, data={"notes": "CCD"})
    assert r.status_code == 200
    pic_id = r.json()["id"]
    got = c.get(f"{base}/point/{pid}/picture/{pic_id}")
    assert got.content == PNG and got.headers["content-type"] == "image/png"
    p = desk.pictures(pid)[-1]
    assert (p.id, p.filename, p.notes) == (pic_id, "beam.png", "CCD")
    assert c.post(f"{base}/point/{pid}/picture", files={"file": ("x.txt", b"hi", "text/plain")}).status_code == 400
    assert c.get(f"{base}/point/{pid}/picture/999999").status_code == 404
    assert _digest(lay) == lay_before  # the layout file is never written
    desk.close()


def test_new_log_from_the_web():
    core.with_qt_loop(_test_new_log_from_the_web)


def _test_new_log_from_the_web():
    """A layout without a log: the first web reading creates it; a desktop
    holding an empty in-memory log switches to that file."""
    d, c = _setup()
    _login(c)
    (d / "demo_399nm.logbook.sqlite").unlink()
    desk = Logbook(d / "demo_399nm.logbook.sqlite")
    assert desk.in_memory and not desk.changed_on_disk()
    base = "/api/layout/0/demo_399nm.json"
    assert not c.get(base).json()["has_log"]
    pid = c.get(base).json()["points"][0]["id"]
    assert not (d / "demo_399nm.logbook.sqlite").exists()  # viewing didn't create it
    c.post(f"{base}/point/{pid}/reading", data={"value": "3"})
    assert (d / "demo_399nm.logbook.sqlite").exists()
    assert desk.changed_on_disk() and not desk.in_memory and desk.power_history(pid)[0].power_mw == 3
    desk.add_power(pid, 4.0)  # and the desktop writes into the same file
    assert len(c.get(f"{base}/point/{pid}").json()["history"]) == 2
    desk.close()


def test_default_folders():
    """Without a config.json: the examples, reachable from this PC only."""
    cfg = core.load_config(core.WEB / "no_such_config.json")
    assert [f.name for f in cfg["folders"]] == ["examples"]
    assert all(f.is_dir() for f in cfg["folders"])
    assert cfg["host"] == "127.0.0.1"
    assert core.load_config(core.WEB / "config.example.json")["host"] == "127.0.0.1"

if __name__ == "__main__":
    test_default_folders()
    test_password()
    test_layouts_read_only()
    test_logging_on_a_copy()
    test_new_log_from_the_web()
    print("ok")
