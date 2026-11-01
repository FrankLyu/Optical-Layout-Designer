"""Power-logger UI: the per-point log window and the points overview panel."""

from __future__ import annotations

import csv
from datetime import datetime

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .logbook import UNITS_TO_MW, Logbook, PowerRecord, format_power

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif);;All files (*)"
MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "bmp": "image/bmp",
        "tif": "image/tiff", "tiff": "image/tiff", "gif": "image/gif"}


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _short_time(iso: str) -> str:
    return _dt(iso).strftime("%Y-%m-%d %H:%M")


class PowerPlot(QWidget):
    """Minimal time-series plot of power vs time (no extra dependencies)."""

    def __init__(self):
        super().__init__()
        self.records: list[PowerRecord] = []
        self.setMinimumHeight(170)

    def set_records(self, records: list[PowerRecord]) -> None:
        self.records = records
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        m_l, m_r, m_t, m_b = 58, 12, 10, 26
        area = QRectF(m_l, m_t, self.width() - m_l - m_r, self.height() - m_t - m_b)
        p.setPen(QPen(QColor("#999999"), 1))
        p.drawRect(area)
        if not self.records:
            p.setPen(QColor("#888888"))
            p.drawText(area, Qt.AlignCenter, "No readings yet")
            return
        ts = [_dt(r.measured_at).timestamp() for r in self.records]
        ys = [r.power_mw for r in self.records]
        t0, t1 = min(ts), max(ts)
        if t1 == t0:
            t0, t1 = t0 - 3600, t1 + 3600
        y0, y1 = min(ys), max(ys)
        pad = (y1 - y0) * 0.15 or abs(y1) * 0.1 or 1
        y0, y1 = y0 - pad, y1 + pad

        def X(t):
            return area.left() + (t - t0) / (t1 - t0) * area.width()

        def Y(y):
            return area.bottom() - (y - y0) / (y1 - y0) * area.height()

        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        p.setPen(QColor("#555555"))
        for frac in (0, 0.5, 1):
            yv = y0 + frac * (y1 - y0)
            p.drawText(QRectF(0, Y(yv) - 7, m_l - 4, 14), Qt.AlignRight | Qt.AlignVCenter, format_power(yv))
        for t, align in ((t0, Qt.AlignLeft), (t1, Qt.AlignRight)):
            p.drawText(QRectF(area.left(), area.bottom() + 4, area.width(), 16), align | Qt.AlignTop,
                       datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M"))
        path = QPainterPath(QPointF(X(ts[0]), Y(ys[0])))
        for t, y in zip(ts[1:], ys[1:]):
            path.lineTo(X(t), Y(y))
        p.setPen(QPen(QColor("#7f3fbf"), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setBrush(QColor("#7f3fbf"))
        for t, y in zip(ts, ys):
            p.drawEllipse(QPointF(X(t), Y(y)), 3, 3)


class PictureViewer(QDialog):
    def __init__(self, data: bytes, title: str, filename: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.data, self.filename = data, filename
        img = QImage.fromData(data)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        if img.isNull():
            lbl.setText("Cannot display this file (it is still stored in the log).")
        else:
            lbl.setPixmap(QPixmap.fromImage(img))
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        save = QPushButton("Save a copy…")
        save.clicked.connect(self._save)
        lay = QVBoxLayout(self)
        lay.addWidget(scroll)
        lay.addWidget(save, 0, Qt.AlignRight)
        self.resize(min(1200, img.width() + 60 if not img.isNull() else 500),
                    min(900, img.height() + 90 if not img.isNull() else 300))

    def _save(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save picture", self.filename)
        if p:
            with open(p, "wb") as fh:
                fh.write(self.data)


class MeasurementDialog(QDialog):
    """Log window for one measurement point: power readings and beam pictures."""

    changed = Signal()

    def __init__(self, logbook: Logbook, point, beam_desc: str, default_wavelength: float | None, parent=None):
        super().__init__(parent)
        self.logbook, self.point = logbook, point
        self.setWindowTitle(f"{point.label} — measurement log")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        logbook.register_point(point.id, point.label)

        head = QLabel(f"<b>{point.label}</b> &nbsp; {beam_desc}"
                      + (" &nbsp; <i>(archived)</i>" if point.archived else "")
                      + f"<br><span style='color:#777'>id {point.id}</span>")
        head.setTextInteractionFlags(Qt.TextSelectableByMouse)

        tabs = QTabWidget()
        tabs.addTab(self._power_tab(default_wavelength), "Power")
        tabs.addTab(self._pictures_tab(), "Beam pictures")
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(tabs)
        self.resize(820, 640)
        self.reload()

    # ---- power -----------------------------------------------------------------
    def _power_tab(self, default_wl):
        w = QWidget()
        self.value = QDoubleSpinBox()
        self.value.setRange(0, 1e6)
        self.value.setDecimals(4)
        self.unit = QComboBox()
        self.unit.addItems(["mW", "µW", "W", "nW"])
        self.instrument = QLineEdit()
        self.instrument.setPlaceholderText("e.g. Thorlabs S120C")
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("e.g. after cleaning PBS")
        add = QPushButton("Add reading")
        add.setDefault(True)
        add.clicked.connect(self._add_reading)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Power"))
        row1.addWidget(self.value, 1)
        row1.addWidget(self.unit)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Meter"))
        row2.addWidget(self.instrument, 1)
        row2.addWidget(QLabel("Notes"))
        row2.addWidget(self.notes, 2)
        row2.addWidget(add)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Measured", "Power", "Meter", "Notes"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.del_btn = QPushButton("Delete selected")
        self.del_btn.setToolTip("Hide the selected readings from the log, the plot and the labels (Del). "
                                "Tick Show deleted to bring them back.")
        self.del_btn.clicked.connect(lambda: self._delete_selected("power"))
        self.restore_btn = QPushButton("Restore selected")
        self.restore_btn.clicked.connect(lambda: self._restore_selected("power"))
        self.show_deleted = QCheckBox("Show deleted")
        self.show_deleted.toggled.connect(lambda _on: self.reload())
        self.plot = PowerPlot()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.plot)
        split.setSizes([300, 200])
        note = QLabel("Deleted readings are only hidden: tick Show deleted to see and restore them.")
        note.setStyleSheet("color:#777")
        row3 = QHBoxLayout()
        row3.addWidget(note, 1)
        row3.addWidget(self.show_deleted)
        row3.addWidget(self.restore_btn)
        row3.addWidget(self.del_btn)

        v = QVBoxLayout(w)
        v.addLayout(row1)
        v.addLayout(row2)
        v.addWidget(split, 1)
        v.addLayout(row3)
        return w

    def _selected_ids(self, kind: str) -> list[int]:
        if kind == "power":
            rows = sorted({i.row() for i in self.table.selectedIndexes()})
            return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]
        return [it.data(Qt.UserRole).id for it in self.pics.selectedItems()]

    def _update_buttons(self):
        gone = self.logbook.deleted_ids("power")
        ids = self._selected_ids("power")
        self.del_btn.setEnabled(any(i not in gone for i in ids))
        self.restore_btn.setVisible(self.show_deleted.isChecked())
        self.restore_btn.setEnabled(any(i in gone for i in ids))
        pgone = self.logbook.deleted_ids("picture")
        pids = self._selected_ids("picture")
        self.pic_del_btn.setEnabled(any(i not in pgone for i in pids))
        self.pic_restore_btn.setVisible(self.pic_show_deleted.isChecked())
        self.pic_restore_btn.setEnabled(any(i in pgone for i in pids))

    def _delete_selected(self, kind: str):
        gone = self.logbook.deleted_ids(kind)
        ids = [i for i in self._selected_ids(kind) if i not in gone]
        if not ids:
            return
        what = ("reading" if kind == "power" else "picture") + ("s" if len(ids) > 1 else "")
        if QMessageBox.question(self, "Delete", f"Delete {len(ids)} {what} from {self.point.label}'s log?\n\n"
                                f"You can bring {'them' if len(ids) > 1 else 'it'} back with Show deleted.") \
                != QMessageBox.Yes:
            return
        self.logbook.set_deleted(kind, ids, True)
        self.reload()
        self.changed.emit()

    def _restore_selected(self, kind: str):
        gone = self.logbook.deleted_ids(kind)
        ids = [i for i in self._selected_ids(kind) if i in gone]
        if ids:
            self.logbook.set_deleted(kind, ids, False)
            self.reload()
            self.changed.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.table.hasFocus():
                self._delete_selected("power")
                return
            if self.pics.hasFocus():
                self._delete_selected("picture")
                return
        super().keyPressEvent(e)

    def _add_reading(self):
        if self.value.value() <= 0:
            QMessageBox.warning(self, "Add reading", "Enter a power above zero.")
            return
        self.logbook.add_power(self.point.id, self.value.value(), self.unit.currentText(),
                               instrument=self.instrument.text().strip(), notes=self.notes.text().strip())
        self.value.setValue(0)
        self.notes.clear()
        self.reload()
        self.changed.emit()

    # ---- pictures --------------------------------------------------------------
    def _pictures_tab(self):
        w = QWidget()
        self.pic_notes = QLineEdit()
        self.pic_notes.setPlaceholderText("Notes for the next picture, e.g. CCD 30 cm after PBS, 1/1000 s")
        add = QPushButton("Add picture files…")
        add.clicked.connect(self._add_files)
        paste = QPushButton("Paste from clipboard")
        paste.clicked.connect(self._paste)
        self.pics = QListWidget()
        self.pics.setViewMode(QListWidget.IconMode)
        self.pics.setIconSize(QSize(180, 135))
        self.pics.setResizeMode(QListWidget.Adjust)
        self.pics.setSpacing(8)
        self.pics.setWordWrap(True)
        self.pics.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.pics.itemDoubleClicked.connect(self._open_pic)
        self.pics.itemSelectionChanged.connect(self._update_buttons)
        self.pic_del_btn = QPushButton("Delete selected")
        self.pic_del_btn.clicked.connect(lambda: self._delete_selected("picture"))
        self.pic_restore_btn = QPushButton("Restore selected")
        self.pic_restore_btn.clicked.connect(lambda: self._restore_selected("picture"))
        self.pic_show_deleted = QCheckBox("Show deleted")
        self.pic_show_deleted.toggled.connect(lambda _on: self.reload())
        row = QHBoxLayout()
        row.addWidget(self.pic_notes, 1)
        row.addWidget(add)
        row.addWidget(paste)
        v = QVBoxLayout(w)
        v.addLayout(row)
        v.addWidget(self.pics, 1)
        hint = QLabel("Pictures (beam profiles, camera shots) are stored inside the logbook file. "
                      "Double-click to view or save a copy.")
        hint.setStyleSheet("color:#777")
        row2 = QHBoxLayout()
        row2.addWidget(hint, 1)
        row2.addWidget(self.pic_show_deleted)
        row2.addWidget(self.pic_restore_btn)
        row2.addWidget(self.pic_del_btn)
        v.addLayout(row2)
        return w

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add beam pictures", "", IMAGE_FILTER)
        for path in paths:
            with open(path, "rb") as fh:
                data = fh.read()
            name = path.replace("\\", "/").split("/")[-1]
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            self.logbook.add_picture(self.point.id, data, name, MIME.get(ext, "application/octet-stream"),
                                     notes=self.pic_notes.text().strip())
        if paths:
            self.pic_notes.clear()
            self.reload()
            self.changed.emit()

    def add_image(self, img: QImage, name: str = "") -> None:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        name = name or f"{self.point.label}_{datetime.now():%Y%m%d_%H%M%S}.png"
        self.logbook.add_picture(self.point.id, bytes(QByteArray(buf.data())), name, "image/png",
                                 notes=self.pic_notes.text().strip())
        self.pic_notes.clear()
        self.reload()
        self.changed.emit()

    def _paste(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            QMessageBox.information(self, "Paste", "The clipboard has no image.")
            return
        self.add_image(img)

    def _open_pic(self, item):
        rec = item.data(Qt.UserRole)
        PictureViewer(self.logbook.picture_data(rec.id), f"{self.point.label} — {_short_time(rec.taken_at)}",
                      rec.filename, self).exec()

    # ---- refresh -------------------------------------------------------------------
    def reload(self):
        gone = self.logbook.deleted_ids("power")
        shown = self.logbook.power_history(self.point.id, include_deleted=self.show_deleted.isChecked())
        recs = [r for r in shown if r.id not in gone]  # the plot never shows deleted readings
        self.table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            cells = [_short_time(r.measured_at), format_power(r.power_mw), r.instrument or "",
                     ("(deleted) " if r.id in gone else "") + (r.notes or "")]
            for j, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                it.setData(Qt.UserRole, r.id)
                if j == 1:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if r.id in gone:
                    f = it.font()
                    f.setStrikeOut(True)
                    it.setFont(f)
                    it.setForeground(QColor("#999999"))
                self.table.setItem(i, j, it)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.scrollToBottom()
        self.plot.set_records(recs)

        self.pics.clear()
        pgone = self.logbook.deleted_ids("picture")
        for rec in reversed(self.logbook.pictures(self.point.id, include_deleted=self.pic_show_deleted.isChecked())):
            img = QImage.fromData(self.logbook.picture_data(rec.id))
            icon = QIcon(QPixmap.fromImage(img.scaled(360, 270, Qt.KeepAspectRatio, Qt.SmoothTransformation))) \
                if not img.isNull() else QIcon()
            text = (("(deleted) " if rec.id in pgone else "") + _short_time(rec.taken_at)
                    + (f"\n{rec.notes}" if rec.notes else ""))
            it = QListWidgetItem(icon, text)
            if rec.id in pgone:
                it.setForeground(QColor("#999999"))
            it.setData(Qt.UserRole, rec)
            it.setToolTip(rec.filename)
            self.pics.addItem(it)
        self._update_buttons()


class PointsPanel(QWidget):
    """Overview of all measurement points with their latest reading."""

    open_point = Signal(str)
    show_archived_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Point", "Latest", "Change", "Measured", "Pics"])
        self.table.horizontalHeaderItem(2).setToolTip("Change from the reading before the latest one")
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.open_point.emit(self.table.item(r, 0).data(Qt.UserRole)))
        self.archived = QCheckBox("Show archived points on the table")
        self.archived.toggled.connect(self.show_archived_changed)
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.addWidget(self.table, 1)
        v.addWidget(self.archived)
        hint = QLabel("Double-click a row (or click a marker) to open its log.")
        hint.setStyleSheet("color:#777")
        v.addWidget(hint)

    def refresh(self, points: list, latest: dict, pic_counts: dict) -> None:
        self.table.setRowCount(len(points))
        for i, pt in enumerate(sorted(points, key=lambda p: (p.archived, _label_key(p.label)))):
            lt = latest.get(pt.id)
            change, pct = "", None
            if lt and lt[1] is not None and lt[1].power_mw:
                pct = (lt[0].power_mw - lt[1].power_mw) / lt[1].power_mw * 100
                change = f"{pct:+.0f} %"
            vals = [pt.label + (" (archived)" if pt.archived else ""), format_power(lt[0].power_mw) if lt else "—",
                    change, _short_time(lt[0].measured_at) if lt else "", str(pic_counts.get(pt.id, ""))]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 0:
                    it.setData(Qt.UserRole, pt.id)
                if j in (1, 2, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if pt.archived:
                    it.setForeground(QColor("#888888"))
                elif j == 2 and pct is not None and abs(pct) >= 10:
                    it.setForeground(QColor("#d62728") if pct < 0 else QColor("#2ca02c"))
                self.table.setItem(i, j, it)
        self.table.resizeColumnsToContents()


def _label_key(label: str):
    digits = "".join(ch for ch in label if ch.isdigit())
    return (int(digits) if digits else 1 << 30, label)


def export_power_csv(logbook: Logbook, labels: dict[str, str], path: str) -> int:
    gone = logbook.deleted_ids("power")
    rows = [r for r in logbook.db.execute(
        "SELECT point_id, measured_at, power_mw, unit, wavelength_nm, instrument, notes, id, created_at"
        " FROM power ORDER BY point_id, measured_at, id") if r[7] not in gone]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["point", "point_id", "measured_at", "power_mW", "entered_unit", "wavelength_nm", "meter",
                    "notes", "record_id", "written_at"])
        for r in rows:
            w.writerow([labels.get(r[0], ""), *r])
    return len(rows)


__all__ = ["MeasurementDialog", "PointsPanel", "PowerPlot", "export_power_csv", "UNITS_TO_MW"]
