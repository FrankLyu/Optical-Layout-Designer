"""Web viewer and power logger for the Optical Layout Designer.

    py -3.13 web/server.py            (settings in web/config.json)

Any PC on the network then opens http://<this PC>:8000. Layouts are only
viewed here (the desktop app edits them); readings and beam pictures go into
the same power log the desktop uses."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from web import core  # noqa: E402

STATIC = core.WEB / "static"
UNITS = ["mW", "µW", "W", "nW"]
COOKIE = "optolayout_web"
MAX_PICTURE = 30_000_000


def _token(password: str) -> str:
    return hmac.new(password.encode(), b"optolayout-web", hashlib.sha256).hexdigest()


def create_app(cfg: dict | None = None) -> FastAPI:
    cfg = cfg or core.load_config()
    # cfg["extra_folders"]: optional callable giving more folders (the desktop app adds the open layout's)
    extra = cfg.get("extra_folders") or (lambda: [])

    def folders() -> list[Path]:
        out = list(cfg["folders"])
        return out + [f for f in extra() if f not in out]
    password = cfg.get("password") or ""
    app = FastAPI(title="Optical Layout Designer (web)", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=2000)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def login_required(request: Request, call_next):
        p = request.url.path
        if password and not (p.startswith("/static/") or p in ("/login", "/favicon.ico")):
            if not hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(password)):
                if p.startswith("/api/"):
                    return JSONResponse({"detail": "log in first"}, status_code=401)
                return RedirectResponse("/login?next=" + p, status_code=303)
        return await call_next(request)

    def path_of(fi: int, name: str) -> Path:
        p = core.layout_path(folders(), fi, name)
        if p is None:
            raise HTTPException(404, "no such layout")
        return p

    # ---- pages ------------------------------------------------------------------------
    def page(name: str) -> FileResponse:
        return FileResponse(STATIC / name, headers={"Cache-Control": "no-cache"})

    @app.get("/", response_class=HTMLResponse)
    def home():
        return page("home.html")

    @app.get("/layout/{fi}/{name}", response_class=HTMLResponse)
    def layout_page(fi: int, name: str):
        path_of(fi, name)
        return page("layout.html")

    @app.get("/layout/{fi}/{name}/point/{pid}", response_class=HTMLResponse)
    def point_page(fi: int, name: str, pid: str):
        path_of(fi, name)
        return page("point.html")

    @app.get("/login", response_class=HTMLResponse)
    def login_page():
        return page("login.html")

    @app.post("/login")
    def login(password_: str = Form("", alias="password"), next_: str = Form("/", alias="next")):
        if not password or hmac.compare_digest(password_, password):
            dest = next_ if next_.startswith("/") and not next_.startswith("//") else "/"
            r = RedirectResponse(dest, status_code=303)
            r.set_cookie(COOKIE, _token(password), max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
            return r
        return RedirectResponse("/login?bad=1", status_code=303)

    @app.get("/logout")
    def logout():
        r = RedirectResponse("/login", status_code=303)
        r.delete_cookie(COOKIE)
        return r

    # ---- layouts ------------------------------------------------------------------------
    @app.get("/api/layouts")
    def layouts():
        fs = folders()
        return {"layouts": core.list_layouts(fs), "folders": [f.name for f in fs]}

    @app.get("/api/layout/{fi}/{name}")
    def layout(fi: int, name: str):
        return core.run_qt(core.layout_info, path_of(fi, name))

    @app.get("/api/layout/{fi}/{name}/2d")
    def layout_2d(fi: int, name: str):
        r = core.run_qt(core.render_2d, path_of(fi, name))
        return {"width": r["width"], "height": r["height"], "points": r["points"]}

    @app.get("/api/layout/{fi}/{name}/2d.svg")
    def layout_svg(fi: int, name: str):
        r = core.run_qt(core.render_2d, path_of(fi, name))
        return Response(r["svg"], media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})

    @app.get("/api/layout/{fi}/{name}/picture.png")
    def layout_png(fi: int, name: str, w: int = 1400):
        png = core.run_qt(core.render_png, path_of(fi, name), max(200, min(w, 4000)))
        return Response(png, media_type="image/png")

    @app.get("/api/layout/{fi}/{name}/stamp")
    def layout_stamp(fi: int, name: str):
        return {"stamp": core.stamp(path_of(fi, name))}

    @app.get("/layout/{fi}/{name}/sheet", response_class=HTMLResponse)
    def sheet(fi: int, name: str, points: str | None = None, log: int = 1, history: int = 1, pic: int = 1):
        p = path_of(fi, name)
        info = core.run_qt(core.layout_info, p)
        chosen = [x for x in points.split(",") if x] if points is not None else None
        body = core.lab_sheet_html(p, chosen, bool(log), history, bool(pic))
        lay_sheet = core.run_qt(lambda: core.loaded(p).layout.lab_sheet)
        selected = set(chosen if chosen is not None else lay_sheet.points)
        boxes = "".join(
            f"<label><input type='checkbox' name='pt' value='{d['id']}'{' checked' if d['id'] in selected else ''}>"
            f" {d['label']}{' · ' + _esc(d['name']) if d['name'] else ''}</label> " for d in info["points"])
        tpl = (STATIC / "sheet.html").read_text(encoding="utf-8")
        return tpl.replace("{{BOXES}}", boxes).replace("{{SHEET}}", _body_of(body)) \
            .replace("{{LOG}}", " checked" if log else "").replace("{{PIC}}", " checked" if pic else "") \
            .replace("{{HISTORY}}", str(max(1, history))).replace("{{TITLE}}", _esc(info["title"]))

    # ---- power log ----------------------------------------------------------------------
    @app.get("/api/layout/{fi}/{name}/point/{pid}")
    def point(fi: int, name: str, pid: str):
        info = core.point_log(path_of(fi, name), pid)
        if info is None:
            raise HTTPException(404, "no such point")
        info["units"] = UNITS
        return info

    @app.post("/api/layout/{fi}/{name}/point/{pid}/reading")
    def reading(fi: int, name: str, pid: str, value: float = Form(...), unit: str = Form("mW"),
                meter: str = Form(""), notes: str = Form("")):
        p = path_of(fi, name)
        if core.point_log(p, pid) is None:
            raise HTTPException(404, "no such point")
        if not value > 0 or unit not in UNITS:
            raise HTTPException(400, "enter a power above zero")
        rid = core.add_reading(p, pid, value, unit, meter, notes)
        return {"id": rid}

    @app.post("/api/layout/{fi}/{name}/point/{pid}/picture")
    async def upload(fi: int, name: str, pid: str, file: UploadFile = File(...), notes: str = Form("")):
        p = path_of(fi, name)
        data = await file.read()
        if not data or len(data) > MAX_PICTURE:
            raise HTTPException(400, "empty or too large (30 MB at most)")
        mime = file.content_type or "application/octet-stream"
        if not mime.startswith("image/"):
            raise HTTPException(400, "not an image")
        fname = Path(file.filename or "picture.jpg").name
        rid = await _in_thread(lambda: core.point_log(p, pid) and core.add_picture(p, pid, data, fname, mime, notes))
        if not rid:
            raise HTTPException(404, "no such point")
        return {"id": rid}

    @app.get("/api/layout/{fi}/{name}/point/{pid}/picture/{pic_id}")
    def picture(fi: int, name: str, pid: str, pic_id: int):
        r = core.picture(path_of(fi, name), pid, pic_id)
        if r is None:
            raise HTTPException(404, "no such picture")
        return Response(r[0], media_type=r[1], headers={"Cache-Control": "max-age=86400"})

    return app


async def _in_thread(fn):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn)


def _esc(s: str) -> str:
    import html
    return html.escape(s)


def _body_of(doc: str) -> str:
    return doc.split("<body>", 1)[-1].rsplit("</body>", 1)[0]


def main():
    import uvicorn
    cfg = core.load_config(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None)  # default web/config.json
    app = create_app(cfg)
    server = uvicorn.Server(uvicorn.Config(app, host=cfg["host"], port=int(cfg["port"]), log_level="info"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    print(f"Optical Layout Designer web: http://localhost:{cfg['port']}  (folders: "
          + ", ".join(str(f) for f in cfg["folders"]) + ")  Ctrl+C to stop", flush=True)
    import signal
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    try:
        core.qt_loop(lambda: stop["now"] or not t.is_alive())  # Qt drawing on this (main) thread
    finally:
        server.should_exit = True
        t.join(5)


if __name__ == "__main__":
    main()
