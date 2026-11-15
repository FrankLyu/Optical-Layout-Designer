"""The photo-to-layout chat for the promo: Jiahao sends the board photo, then his
red beam sketch, to an AI assistant using the skills/photo-to-layout skill.

    py -3.13 promo/chat.py      -> promo/out/photo_chat.mp4 (1920x1080, 30 fps)

A plain, generic chat window drawn with Qt, in the app's dark-studio colours. The
pictures are the real ones from skills/photo-to-layout/example/rounds_comparison.png
(the round-1 photo and the round-2 sketch), cropped to the board.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen, \
    QRadialGradient
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edit import FFMPEG, H, W, FPS, OUT, ease  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "photo-to-layout" / "example" / "rounds_comparison.png"
PHOTO_CROP = (87, 11, 583, 562)  # x, y, w, h in rounds_comparison.png: the board photo
SKETCH_CROP = (100, 1288, 650, 605)  # the round-2 input: layout with the beams drawn in red

from edit import LANG, SUFFIX  # noqa: E402  (--lang zh: the Chinese chat, photo_chat_zh.mp4)

USER = "Jiahao"
BOT_DOTS = 0.75  # s of "typing" dots before the assistant's answer
if LANG == "zh":
    BOT, PLACEHOLDER = "AI 助手", "给助手发消息…"
    # (who, picture or None, text, the time it is sent in s); the user's text is typed in the box first
    SCRIPT = [
        ("user", "photo", "这是我们 421 nm 低功率光路板的照片，能帮我转成布局吗？", 4.4),
        ("bot", None, "已根据照片放好元件。光路怎么走？", 5.4),
        ("user", "sketch", "光路用红线画出来了。", 7.7),
        ("bot", None, "完成。光路已连好，已打开 Dy1-lowpower.json。", 8.8),
    ]
    TYPE_CPS = 8  # whole characters, at a natural pace
    DURATION = 10.8
else:
    BOT, PLACEHOLDER = "AI assistant", "Message the assistant…"
    SCRIPT = [
        ("user", "photo", "Here's our 421 nm low-power board. Can you turn it into a layout?", 2.75),
        ("bot", None, "Placed the parts from the photo. How does the beam go?", 3.75),
        ("user", "sketch", "Beam path drawn in red.", 6.35),
        ("bot", None, "Done. Routed the beams, opened Dy1-lowpower.json.", 7.45),
    ]
    TYPE_CPS = 32  # the user's typing speed
    DURATION = 9.6

# window
WX, WY, WW, WH = 360, 50, 1200, 740  # leaves the lower third free for the caption
BAR = 46
INPUT_H = 92
PAD = 30
THUMB_W = 400
BG = QColor("#16191f")
PANEL = QColor("#1e222a")
USER_BUB = QColor("#5a4790")
BOT_BUB = QColor("#2c313b")
TEXT = QColor("#f2f2f5")
MUTED = QColor("#9aa0ab")
ACCENT = QColor(183, 127, 208)


def font(px, weight=QFont.Normal):
    f = QFont("Segoe UI")
    f.setFamilies(["Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"])
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


F_MSG = font(25)
F_NAME = font(18, QFont.DemiBold)
F_TITLE = font(19, QFont.DemiBold)


def pictures():
    src = QImage(str(SOURCE))
    out = {}
    for key, (x, y, w, h) in (("photo", PHOTO_CROP), ("sketch", SKETCH_CROP)):
        img = src.copy(x, y, w, h)
        out[key] = img.scaledToWidth(THUMB_W, Qt.SmoothTransformation)
    return out


def text_h(text, width):
    fm = QFontMetricsF(F_MSG)
    return fm.boundingRect(QRectF(0, 0, width, 2000), Qt.TextWordWrap, text).height()


def bubble_size(text, pic, pics):
    fm = QFontMetricsF(F_MSG)
    if pic:  # as wide as the picture, the text wrapped under it
        tw = THUMB_W - 20
    else:
        tw = min(680, fm.horizontalAdvance(text) + 2)
    th = text_h(text, tw) if text else 0
    w = tw + 2 * 20
    h = th + 2 * 14
    if pic:
        h += pics[pic].height() + 10
    return w, h


def draw_frame(t: float, pics, state) -> QImage:
    img = QImage(W, H, QImage.Format_RGB888)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    g = QLinearGradient(0, 0, 0, H)  # the desk behind the window
    g.setColorAt(0, QColor("#1a1e27"))
    g.setColorAt(1, QColor("#0b0d12"))
    p.fillRect(QRectF(0, 0, W, H), g)
    glow = QRadialGradient(QPointF(W / 2, 420), 900)
    glow.setColorAt(0, QColor(183, 127, 208, 34))
    glow.setColorAt(1, QColor(183, 127, 208, 0))
    p.fillRect(QRectF(0, 0, W, H), glow)

    k = ease(t / 0.4)  # the window comes up
    p.setOpacity(k)
    win = QRectF(WX, WY + (1 - k) * 16, WW, WH)
    for i in range(14, 0, -2):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 10))
        p.drawRoundedRect(win.adjusted(-i, -i + 6, i, i + 6), 14 + i, 14 + i)
    clip = QPainterPath()
    clip.addRoundedRect(win, 12, 12)
    p.save()
    p.setClipPath(clip)
    p.fillRect(win, BG)
    bar = QRectF(win.left(), win.top(), win.width(), BAR)
    p.fillRect(bar, PANEL)
    p.setPen(QColor(255, 255, 255, 18))
    p.drawLine(bar.bottomLeft(), bar.bottomRight())
    for i, c in enumerate(("#5b606b", "#5b606b", "#5b606b")):  # neutral window dots
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c))
        p.drawEllipse(QPointF(bar.left() + 24 + 22 * i, bar.center().y()), 6, 6)
    p.setFont(F_TITLE)
    p.setPen(TEXT)
    p.drawText(bar, Qt.AlignCenter, BOT)

    # messages
    area = QRectF(win.left(), bar.bottom(), win.width(), win.height() - BAR - INPUT_H)
    sent = [m for m in SCRIPT if t >= m[3]]
    items = []  # (kind, who, pic, text, appear_time)
    for who, pic, text, ts in sent:
        items.append(("msg", who, pic, text, ts))
    nxt = next((m for m in SCRIPT if t < m[3]), None)
    if nxt and nxt[0] == "bot" and t >= nxt[3] - BOT_DOTS:
        items.append(("dots", "bot", None, "", nxt[3] - BOT_DOTS))
    # heights, stacked from the top; scroll so the newest stays in view
    y = PAD
    placed = []
    for kind, who, pic, text, ts in items:
        if kind == "dots":
            w, h = 96, 54
        else:
            w, h = bubble_size(text, pic, pics)
        placed.append((kind, who, pic, text, ts, y, w, h))
        y += 26 + h + 22
    target = max(0.0, y - area.height())
    state["scroll"] += (target - state["scroll"]) * 0.22
    p.save()
    p.setClipRect(area)
    for kind, who, pic, text, ts, yy, w, h in placed:
        a = ease((t - ts) / 0.25)
        p.setOpacity(k * a)
        top = area.top() + yy - state["scroll"] + (1 - a) * 14
        user = who == "user"
        av = QPointF(area.right() - PAD - 20, top + 14) if user else QPointF(area.left() + PAD + 20, top + 14)
        p.setPen(Qt.NoPen)
        p.setBrush(USER_BUB if user else QColor("#3a4150"))
        p.drawEllipse(av, 18, 18)
        p.setPen(TEXT)
        p.setFont(font(17, QFont.Bold))
        p.drawText(QRectF(av.x() - 18, av.y() - 18, 36, 36), Qt.AlignCenter, "J" if user else "AI")
        p.setFont(F_NAME)
        p.setPen(MUTED)
        name_r = QRectF(area.left() + PAD + 50, top + 2, 400, 24) if not user else \
            QRectF(area.right() - PAD - 50 - 400, top + 2, 400, 24)
        p.drawText(name_r, (Qt.AlignRight if user else Qt.AlignLeft) | Qt.AlignVCenter, USER if user else BOT)
        bx = area.right() - PAD - 50 - w if user else area.left() + PAD + 50
        b = QRectF(bx, top + 30, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(USER_BUB if user else BOT_BUB)
        p.drawRoundedRect(b, 16, 16)
        if kind == "dots":
            for i in range(3):
                ph = (t * 5 - i * 0.6)
                r = 5 + 1.6 * max(0.0, math.sin(ph))
                p.setBrush(QColor(220, 222, 230, 150 + int(90 * max(0.0, math.sin(ph)))))
                p.drawEllipse(QPointF(b.left() + 28 + i * 20, b.center().y()), r, r)
            continue
        cy = b.top() + 10
        if pic:
            im = pics[pic]
            r = QRectF(b.left() + 10, cy, im.width(), im.height())
            path = QPainterPath()
            path.addRoundedRect(r, 10, 10)
            p.save()
            p.setClipPath(path, Qt.IntersectClip)
            p.drawImage(r, im)
            p.restore()
            cy += im.height() + 6
        p.setPen(TEXT)
        p.setFont(F_MSG)
        p.drawText(QRectF(b.left() + 20, cy + 4, w - 40, b.bottom() - cy - 8), Qt.TextWordWrap | Qt.AlignLeft
                   | Qt.AlignVCenter, text)
    p.restore()
    p.setOpacity(k)

    # the input box: the user's next message is typed here, with its picture attached
    box = QRectF(win.left() + PAD, win.bottom() - INPUT_H + 16, win.width() - 2 * PAD, INPUT_H - 32)
    p.setPen(QPen(QColor(255, 255, 255, 30), 1.2))
    p.setBrush(PANEL)
    p.drawRoundedRect(box, box.height() / 2, box.height() / 2)
    typed, chip = "", None
    prev_t = 0.0
    for who, pic, text, ts in SCRIPT:
        if who == "user" and prev_t <= t < ts:
            start = ts - len(text) / TYPE_CPS - 0.25
            if t >= start - 0.45:
                chip = pic
            n = max(0, min(len(text), int((t - start) * TYPE_CPS)))
            typed = text[:n]
            break
        prev_t = ts
    x = box.left() + 26
    if chip:
        im = pics[chip]
        th = box.height() - 14
        tw = im.width() * th / im.height()
        r = QRectF(x - 12, box.top() + 7, tw, th)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.save()
        p.setClipPath(path, Qt.IntersectClip)
        p.drawImage(r, im)
        p.restore()
        x = r.right() + 14
    p.setFont(F_MSG)
    if typed:
        p.setPen(TEXT)
        p.drawText(QRectF(x, box.top(), box.right() - x - 80, box.height()), Qt.AlignLeft | Qt.AlignVCenter, typed)
        if int(t * 2.4) % 2 == 0:  # caret
            cx = x + QFontMetricsF(F_MSG).horizontalAdvance(typed) + 2
            p.fillRect(QRectF(cx, box.center().y() - 14, 2, 28), TEXT)
    elif not chip:
        p.setPen(MUTED)
        p.drawText(QRectF(x, box.top(), box.width() - 120, box.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   PLACEHOLDER)
    send = QPointF(box.right() - 34, box.center().y())  # send button
    p.setPen(Qt.NoPen)
    p.setBrush(ACCENT if typed else QColor("#3a4150"))
    p.drawEllipse(send, 21, 21)
    p.setBrush(QColor("#ffffff"))
    arrow = [QPointF(send.x() - 8, send.y() + 8), QPointF(send.x() + 9, send.y()), QPointF(send.x() - 8, send.y() - 8),
             QPointF(send.x() - 4, send.y())]
    from PySide6.QtGui import QPolygonF
    p.drawPolygon(QPolygonF(arrow))
    p.restore()
    p.setPen(QPen(QColor(255, 255, 255, 26), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(win, 12, 12)
    p.end()
    return img


def main():
    app = QApplication(sys.argv[:1])  # noqa: F841
    pics = pictures()
    out = OUT / f"photo_chat{SUFFIX}.mp4"
    proc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                             f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset", "slow",
                             "-crf", "16", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    state = {"scroll": 0.0}
    n = round(DURATION * FPS)
    for i in range(n):
        img = draw_frame(i / FPS, pics, state)
        proc.stdin.write(bytes(img.constBits())[: W * H * 3])
        if i == round(5.6 * FPS):
            img.save(str(OUT / "stills" / f"photo_chat{SUFFIX}.png"))
    proc.stdin.close()
    proc.wait()
    print(f"{out}  {n / FPS:.2f} s")


if __name__ == "__main__":
    main()
