"""Cut the promo from the clips capture.py made (promo/out/<scene>.mp4).

    py -3.13 promo/edit.py

ffmpeg decodes the clips and encodes the result; each frame is put together
here (trims, speed-ups, 0.3 s crossfades, title / captions / end card drawn
with Qt). Outputs, all in promo/out/:
    promo.mp4            the cut (<= 30 s, 1920x1080, 30 fps, H.264 crf 18, no audio)
    promo_web.mp4        only when promo.mp4 is over 10 MB (crf 23)
    promo_readme.gif     ~11 s loop of the layout-drag and live-3D parts, 960 px, 15 fps
    stills/final_*.png   a few frames of the cut, for checking
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen, \
    QRadialGradient
from PySide6.QtWidgets import QApplication

# ---- settings ---------------------------------------------------------------------------------
GITHUB_URL = ""  # e.g. "github.com/<user>/optical-layout-designer"; empty: the line is left out

# --lang zh: the Simplified Chinese cut (promo_zh.mp4); the app itself stays English
LANG = "zh" if "--lang" in sys.argv and sys.argv[sys.argv.index("--lang") + 1:][:1] == ["zh"] else "en"
TEXT = {
    "en": dict(title="Optical Layout Designer", subtitle="Plan, build and log your optical table",
               end="Open source · MIT · © Jiahao Lyu",
               schematic="Pick the exact mount and part number in the schematic",
               layout="Drag mounts on the real hole grid, add power points anywhere",
               chat="Photo + sketch to layout with the AI skill",
               live3d="Live 3D from the 2D layout",
               power="Log beam power right on the table",
               labsheet="Lab sheet with readings and notes, ready for OneNote or Excel"),
    "zh": dict(title="Optical Layout Designer", subtitle="光学平台布局设计器：规划、搭建、记录光路",
               end="开源 · MIT 许可 · © Jiahao Lyu",
               schematic="在原理图中选择具体镜架和型号",
               layout="在真实孔位上拖动镜架，光路自动跟随；随处添加功率测量点",
               chat="AI 技能：照片 + 草图，一键生成布局",
               live3d="由二维布局实时生成三维视图",
               power="直接在光学平台上记录光功率",
               labsheet="实验记录表：读数与备注，可直接粘贴到 OneNote 或 Excel"),
}[LANG]
SUFFIX = "" if LANG == "en" else f"_{LANG}"
TITLE, SUBTITLE, END_LINE = TEXT["title"], TEXT["subtitle"], TEXT["end"]

OUT = Path(__file__).resolve().parent / "out"
W, H, FPS = 1920, 1080, 30
XFADE = 0.3  # s
FONT = "Segoe UI"
FONTS = ["Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"]  # Latin in Segoe UI, Chinese in Microsoft YaHei

# clip, source in/out (s), speed, caption ("" = none), title overlay
SEGMENTS = [
    dict(clip="title_orbit", t0=0.0, t1=3.0, speed=1.0, caption="", title=True),
    dict(clip="schematic", t0=0.5, t1=9.4, speed=1.0, caption=TEXT["schematic"]),
    dict(clip="layout_drag", t0=0.3, t1=8.0, speed=1.0, caption=TEXT["layout"]),
    dict(clip="photo_chat" + SUFFIX, t0=0.0, t1=9.6 if LANG == "en" else 10.8, speed=1.0, caption=TEXT["chat"]),
    dict(clip="dy1_layout", t0=0.0, t1=2.6, speed=1.0, caption=""),  # the layout that chat made
    dict(clip="live3d", t0=0.75, t1=7.8, speed=1.2, caption=TEXT["live3d"]),
    dict(clip="power_log", t0=0.6, t1=5.2, speed=1.0, caption=TEXT["power"], cx=0.22),  # left of the log window
    dict(clip="labsheet" + SUFFIX, t0=1.0, t1=11.9 if LANG == "en" else 12.4, speed=1.0, caption=TEXT["labsheet"]),
    dict(end=True, dur=2.1),
]
GIF_SEGMENTS = [  # the most visual parts: mirror drag + new power point, then live 3D
    dict(clip="layout_drag", t0=0.3, t1=7.0, speed=1.0, caption=TEXT["layout"]),
    dict(clip="live3d", t0=0.75, t1=6.2, speed=1.0, caption=TEXT["live3d"]),
]


def find_tool(name: str) -> str:
    exe = shutil.which(name)
    if exe:
        return exe
    link = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe"
    if link.exists():
        return str(link)
    sys.exit(f"{name} not found: winget install Gyan.FFmpeg")


FFMPEG = find_tool("ffmpeg")


# ---- drawing helpers ------------------------------------------------------------------------

def font(px: float, weight=QFont.DemiBold) -> QFont:
    f = QFont(FONT)
    f.setFamilies(FONTS)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


def as_qimage(a: np.ndarray) -> QImage:
    return QImage(a.data, W, H, 3 * W, QImage.Format_RGB888)


def draw_caption(p: QPainter, text: str, alpha: float, rise: float, cx: float = 0.5):
    f = font(40)
    fm = QFontMetricsF(f)
    tw = fm.horizontalAdvance(text)
    pad_x, h = 38, 74
    r = QRectF(W * cx - tw / 2 - pad_x, 818 + rise, tw + 2 * pad_x, h)  # above the capture's key badge (y > 925)
    p.setOpacity(alpha)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(12, 14, 20, 40))
    p.drawRoundedRect(r.adjusted(-3, -1, 3, 5), h / 2 + 3, h / 2 + 3)  # soft shadow
    p.setBrush(QColor(16, 18, 26, 215))
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setPen(QPen(QColor(255, 255, 255, 40), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(r, Qt.AlignCenter, text)
    p.setOpacity(1)


def draw_title(p: QPainter, alpha: float, rise: float):
    p.setOpacity(alpha)
    g = QRadialGradient(QPointF(W / 2, 520), 900)  # darken the middle a little for the text
    g.setColorAt(0, QColor(8, 10, 16, 170))
    g.setColorAt(0.55, QColor(8, 10, 16, 90))
    g.setColorAt(1, QColor(8, 10, 16, 0))
    p.fillRect(QRectF(0, 0, W, H), g)
    p.setFont(font(104, QFont.Bold))
    p.setPen(QColor(0, 0, 0, 120))
    p.drawText(QRectF(0, 420 + rise + 3, W, 130), Qt.AlignCenter, TITLE)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(0, 420 + rise, W, 130), Qt.AlignCenter, TITLE)
    p.setFont(font(44, QFont.Normal))
    p.setPen(QColor(222, 214, 245))
    p.drawText(QRectF(0, 592 + rise * 1.4, W, 70), Qt.AlignCenter, SUBTITLE)
    p.setPen(Qt.NoPen)  # a thin violet rule, the beam colour
    p.setBrush(QColor(183, 127, 208))
    p.drawRoundedRect(QRectF(W / 2 - 90, 576 + rise * 1.2, 180, 4), 2, 2)
    p.setOpacity(1)


def end_card(t: float) -> np.ndarray:
    img = QImage(W, H, QImage.Format_RGB888)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    g = QLinearGradient(0, 0, 0, H)
    g.setColorAt(0, QColor("#1a1e27"))
    g.setColorAt(1, QColor("#0b0d12"))
    p.fillRect(QRectF(0, 0, W, H), g)
    glow = QRadialGradient(QPointF(W / 2, H / 2), 700)
    glow.setColorAt(0, QColor(183, 127, 208, 40))
    glow.setColorAt(1, QColor(183, 127, 208, 0))
    p.fillRect(QRectF(0, 0, W, H), glow)
    k = min(1.0, t / 0.5)
    rise = (1 - ease(k)) * 14
    lines = [(TITLE, font(96, QFont.Bold), QColor("#ffffff"), 130)]
    lines.append((END_LINE, font(40, QFont.Normal), QColor(205, 208, 220), 70))
    if GITHUB_URL:
        lines.append((GITHUB_URL, font(36, QFont.DemiBold), QColor(196, 160, 222), 64))
    total = sum(h for *_x, h in lines) + 40
    y = (H - total) / 2 + rise
    for i, (txt, f, c, h) in enumerate(lines):
        p.setFont(f)
        p.setPen(c)
        p.drawText(QRectF(0, y, W, h), Qt.AlignCenter, txt)
        y += h
        if i == 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(183, 127, 208))
            p.drawRoundedRect(QRectF(W / 2 - 90, y + 24, 180, 4), 2, 2)
            y += 56
    p.end()
    return qimage_to_array(img)


def qimage_to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format_RGB888)
    b = np.frombuffer(img.constBits(), np.uint8, count=img.sizeInBytes())
    return b.reshape(H, img.bytesPerLine())[:, : W * 3].reshape(H, W, 3).copy()


def ease(t: float) -> float:
    import math
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


# ---- frames of one segment ---------------------------------------------------------------------

def seg_frames(seg: dict) -> tuple[int, "iter"]:
    """(number of output frames, iterator of HxWx3 uint8 frames with the overlays drawn)."""
    if seg.get("end"):
        n = round(seg["dur"] * FPS)
        return n, (end_card(i / FPS) for i in range(n))
    src = OUT / f"{seg['clip']}.mp4"
    t0, t1, speed = seg["t0"], seg["t1"], seg["speed"]
    n = round((t1 - t0) / speed * FPS)

    def gen():
        proc = subprocess.Popen([FFMPEG, "-loglevel", "error", "-ss", f"{t0:.3f}", "-i", str(src), "-t",
                                 f"{t1 - t0 + 0.2:.3f}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        size = W * H * 3
        src_i, cur = -1, None
        try:
            for i in range(n):
                want = int(round(i * speed))
                while src_i < want:
                    buf = proc.stdout.read(size)
                    if len(buf) < size:
                        break  # clip ended: hold the last frame
                    cur = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
                    src_i += 1
                frame = cur.copy()
                overlay(frame, seg, i / FPS, n / FPS)
                yield frame
        finally:
            proc.stdout.close()
            proc.kill()
            proc.wait()
    return n, gen()


def overlay(frame: np.ndarray, seg: dict, t: float, dur: float):
    cap, title = seg.get("caption"), seg.get("title")
    if not cap and not title:
        return
    img = as_qimage(frame)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    if title:
        k = ease((t - 0.25) / 0.6)  # fades in, stays to the crossfade
        if k > 0:
            draw_title(p, k, (1 - k) * 18)
    if cap:
        a_in = ease((t - 0.35) / 0.35)
        a_out = ease((dur - XFADE - 0.1 - t) / 0.3)
        a = min(a_in, a_out)
        if a > 0:
            draw_caption(p, cap, a, (1 - a_in) * 12, seg.get("cx", 0.5))
    p.end()


# ---- assembling -----------------------------------------------------------------------------

def assemble(segments, sink, scale_w=None):
    """Crossfade the segments one after another into sink(frame); returns the frame count."""
    ov = round(XFADE * FPS)
    tail: deque | None = None
    count = 0
    for k, seg in enumerate(segments):
        n, it = seg_frames(seg)
        last = k == len(segments) - 1
        hold = deque()
        for i, f in enumerate(it):
            if tail and i < ov:
                a = (i + 1) / (ov + 1)
                f = (tail.popleft().astype(np.float32) * (1 - a) + f.astype(np.float32) * a).astype(np.uint8)
            hold.append(f)
            if not last and len(hold) > ov:
                sink(hold.popleft())
                count += 1
            elif last:
                sink(hold.popleft())
                count += 1
        tail = hold if not last else None
    return count


class Encoder:
    def __init__(self, path: Path, crf: int, extra_vf: str | None = None, fps: int = FPS):
        vf = ["-vf", extra_vf] if extra_vf else []
        self.proc = subprocess.Popen(
            [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r",
             str(FPS), "-i", "-", *vf, "-an", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
        self.n = 0
        self.stills: dict[int, str] = {}

    def __call__(self, frame: np.ndarray):
        self.proc.stdin.write(frame.tobytes())
        if self.n in self.stills:
            as_qimage(frame).save(str(OUT / "stills" / self.stills[self.n]))
        self.n += 1

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()


def probe_duration(path: Path) -> float:
    out = subprocess.run([find_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def main():
    app = QApplication(sys.argv[:1])  # noqa: F841 - fonts need a GUI application
    (OUT / "stills").mkdir(parents=True, exist_ok=True)
    for seg in SEGMENTS:
        if not seg.get("end") and not (OUT / f"{seg['clip']}.mp4").exists():
            sys.exit(f"missing {seg['clip']}.mp4: run promo/capture.py first")

    # where each segment starts in the cut (for the stills)
    starts, t = [], 0.0
    for seg in SEGMENTS:
        starts.append(t)
        d = seg["dur"] if seg.get("end") else (seg["t1"] - seg["t0"]) / seg["speed"]
        t += d - XFADE
    idx = {seg.get("clip", "end").removesuffix(SUFFIX) if SUFFIX else seg.get("clip", "end"): i
           for i, seg in enumerate(SEGMENTS)}
    picks = {"final_1_title.png": starts[idx["title_orbit"]] + 2.3,
             "final_2_schematic.png": starts[idx["schematic"]] + 5.0,
             "final_3_layout.png": starts[idx["layout_drag"]] + 6.3,
             "final_4_chat_photo.png": starts[idx["photo_chat"]] + 3.6,
             "final_5_chat_done.png": starts[idx["photo_chat"]] + 8.6,
             "final_6_dy1.png": starts[idx["dy1_layout"]] + 1.2,
             "final_7_live3d.png": starts[idx["live3d"]] + 4.5,
             "final_8_power.png": starts[idx["power_log"]] + 2.6,
             "final_9_labsheet_log.png": starts[idx["labsheet"]] + 5.4,
             "final_10_labsheet.png": starts[idx["labsheet"]] + 9.6,
             "final_11_end.png": starts[idx["end"]] + 1.5}

    promo = OUT / f"promo{SUFFIX}.mp4"
    enc = Encoder(promo, 18)
    enc.stills = {round(v * FPS): k.replace("final_", f"final{SUFFIX}_") for k, v in picks.items()}
    n = assemble(SEGMENTS, enc)
    enc.close()
    size = promo.stat().st_size / 1e6
    print(f"{promo.name}  {n / FPS:.2f} s ({probe_duration(promo):.2f} s by ffprobe), {size:.1f} MB")
    web = OUT / f"promo{SUFFIX}_web.mp4"
    if size > 10:
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(promo), "-an", "-c:v", "libx264", "-preset",
                        "slow", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(web)], check=True)
        print(f"{web.name}  {web.stat().st_size / 1e6:.1f} MB")
    elif web.exists():
        web.unlink()

    if LANG != "en":
        return  # the README gif is made from the English cut
    # README gif: render the two parts to a temporary clip, then palettegen / paletteuse
    tmp = OUT / "_gif_src.mp4"
    enc = Encoder(tmp, 12)
    n = assemble(GIF_SEGMENTS, enc)
    enc.close()
    gif = OUT / "promo_readme.gif"
    for colors, dither in ((256, "bayer:bayer_scale=4"), (160, "bayer:bayer_scale=3"), (96, "bayer:bayer_scale=2")):
        flt = (f"fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
               f"[b][p]paletteuse=dither={dither}:diff_mode=rectangle")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(tmp), "-filter_complex", flt, "-loop", "0",
                        str(gif)], check=True)
        gsize = gif.stat().st_size / 1e6
        print(f"promo_readme.gif  {n / FPS:.2f} s, {colors} colours: {gsize:.1f} MB")
        if gsize < 8:
            break
    tmp.unlink()


if __name__ == "__main__":
    main()
