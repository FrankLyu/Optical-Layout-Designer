"""Printable lab sheet: chosen measurement points with their names, latest
power readings and a picture of the layout, for OneNote, Excel, paper or PDF.

Which points, their names and the options are kept in the layout file
(Layout.lab_sheet), so the same points come up checked next time."""

from __future__ import annotations

import base64
import csv
import html
from dataclasses import replace
from datetime import datetime

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QMimeData, Qt, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QTextDocument
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .logbook import Logbook, PowerRecord, format_power
from .model import LabSheet, Layout

LOG_HEADERS = ["Name", "Point", "Power (mW)", "Meter", "Measured", "Notes"]
BLANK_HEADERS = ["Name", "Point", "Power (mW)", "Notes"]  # no log: columns to fill in by hand
PICTURE_PX = 1400  # width of the layout picture rendered for the sheet
SHOW_PX = 640  # width it is shown at (HTML / page)


def label_key(label: str):
    digits = "".join(ch for ch in label if ch.isdigit())
    return (int(digits) if digits else 1 << 30, label)


def sheet_points(lay: Layout) -> list:
    """Points the sheet can list: not archived, P1, P2, ... order."""
    return sorted((p for p in lay.points.values() if not p.archived), key=lambda p: label_key(p.label))


def recent_readings(logbook: Logbook | None, pid: str, n: int) -> list[PowerRecord]:
    """The last n valid readings of a point, newest first (corrected ones left out)."""
    if logbook is None:
        return []
    recs = logbook.power_history(pid)
    superseded = {r.supersedes for r in recs if r.supersedes}
    return [r for r in recs if r.id not in superseded][-max(1, n):][::-1]


def _mw(v: float) -> str:
    return f"{v:.4g}"


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def sheet_table(lay: Layout, logbook: Logbook | None, sheet: LabSheet) -> tuple[list[str], list[list[str]]]:
    """(headers, rows) of the sheet's table, all cells text. With the log, one
    row per reading (up to sheet.history per point); without, one per point."""
    chosen = set(sheet.points)
    pts = [p for p in sheet_points(lay) if p.id in chosen]
    if not sheet.include_log:
        return BLANK_HEADERS, [[lay.point_name(p.id), p.label, "", ""] for p in pts]
    rows = []
    for p in pts:
        recs = recent_readings(logbook, p.id, sheet.history)
        if not recs:
            rows.append([lay.point_name(p.id), p.label, "", "", "", "no readings"])
        for r in recs:
            rows.append([lay.point_name(p.id), p.label, _mw(r.power_mw), r.instrument or "", _when(r.measured_at),
                         r.notes or ""])
    return LOG_HEADERS, rows


# ---- output formats --------------------------------------------------------------

def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(QByteArray(buf.data()))


def sheet_html(title: str, subtitle: str, headers: list[str], rows: list[list[str]], img_src: str | None = None,
               img_size: tuple[int, int] | None = None) -> str:
    """The sheet as HTML: title, subtitle, picture, bordered table. Styles are
    inline and the table has border/cellpadding attributes too, which is what
    OneNote, Word and Excel read when it is pasted."""
    e = html.escape
    cell = "border:1px solid #444; padding:3px 8px; font-family:Calibri, Arial, sans-serif; font-size:11pt;"
    out = [f"<h2 style='font-family:Calibri, Arial, sans-serif; margin:0'>{e(title)}</h2>",
           f"<p style='font-family:Calibri, Arial, sans-serif; color:#555; margin:2px 0 8px 0'>{e(subtitle)}</p>"]
    if img_src:
        size = f" width='{img_size[0]}' height='{img_size[1]}'" if img_size else ""
        out.append(f"<p><img src='{e(img_src, quote=True)}'{size} alt='layout'></p>")
    out.append("<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse'>")
    out.append("<tr>" + "".join(f"<th style='{cell} background:#e8e8e8; text-align:left'>{e(h)}</th>"
                                for h in headers) + "</tr>")
    num = headers.index("Power (mW)")
    for r in rows:
        out.append("<tr>" + "".join(
            f"<td style='{cell}{' text-align:right;' if j == num else ''}'>{e(v) if v else '&nbsp;'}</td>"
            for j, v in enumerate(r)) + "</tr>")
    out.append("</table>")
    doc = "<html><body>\n" + "\n".join(out) + "\n</body></html>"
    return doc.encode("ascii", "xmlcharrefreplace").decode("ascii")  # µ, · as &#..;: no charset mix-ups on paste


def sheet_tsv(headers: list[str], rows: list[list[str]]) -> str:
    """Tab-separated table (Excel and OneNote turn it into cells)."""
    clean = lambda v: str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ")  # noqa: E731
    return "\r\n".join("\t".join(clean(v) for v in r) for r in [headers, *rows]) + "\r\n"


def fit_size(img: QImage, w: int = SHOW_PX, h: int = 560) -> tuple[int, int]:
    """Display size of the picture: fits in w x h, keeps its shape."""
    if img.isNull() or not img.width() or not img.height():
        return w, h
    k = min(w / img.width(), h / img.height())
    return max(1, round(img.width() * k)), max(1, round(img.height() * k))


def clipboard_mime(title, subtitle, headers, rows, img: QImage | None) -> QMimeData:
    """HTML (picture embedded as base64 PNG) + tab-separated text + the picture."""
    md = QMimeData()
    src = size = None
    if img is not None and not img.isNull():
        src = "data:image/png;base64," + base64.b64encode(png_bytes(img)).decode("ascii")
        size = fit_size(img)
        md.setImageData(img)
    md.setHtml(sheet_html(title, subtitle, headers, rows, src, size))
    md.setText(sheet_tsv(headers, rows))
    return md


def sheet_document(title, subtitle, headers, rows, img: QImage | None) -> QTextDocument:
    """The sheet as a QTextDocument for printing and PDF."""
    doc = QTextDocument()
    src = None
    if img is not None and not img.isNull():
        src = "labsheet-layout.png"
        doc.addResource(QTextDocument.ImageResource, QUrl(src), img)
    doc.setHtml(sheet_html(title, subtitle, headers, rows, src, fit_size(img) if src else None))
    return doc


def print_document(doc: QTextDocument, printer) -> None:
    printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
    doc.print_(printer)


def write_pdf(doc: QTextDocument, path: str) -> None:
    from PySide6.QtPrintSupport import QPrinter
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPageSize(QPageSize.Letter))
    print_document(doc, printer)


def write_csv(headers, rows, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # BOM: Excel reads µ etc. right
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)


def write_xlsx(title, subtitle, headers, rows, path: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Lab sheet"
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([subtitle])
    ws.append([])
    ws.append(headers)
    for c in ws[4]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E8E8E8")
    num = headers.index("Power (mW)")
    for r in rows:
        r = list(r)
        try:
            r[num] = float(r[num]) if r[num] else None
        except ValueError:
            pass
        ws.append(r)
    for j, h in enumerate(headers):
        width = max([len(h)] + [len(str(r[j])) for r in rows]) + 2
        ws.column_dimensions[chr(65 + j)].width = min(60, width)
    wb.save(path)


def has_openpyxl() -> bool:
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        return False


# ---- dialog ---------------------------------------------------------------------

class LabSheetDialog(QDialog):
    """Pick the points for the sheet, name them, and copy / print / save it.

    picture() renders the 2D layout (called only when needed); store(sheet)
    keeps the settings in the layout (an undoable edit, saved with the file)."""

    def __init__(self, lay: Layout, logbook: Logbook | None, layout_name: str, picture, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lab sheet")
        self.lay, self.logbook, self.layout_name = lay, logbook, layout_name
        self._picture_fn, self._store_fn = picture, store
        self._picture: QImage | None = None
        sheet = lay.lab_sheet
        latest = logbook.latest_two() if logbook else {}

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Point", "Name", "Latest", "Measured"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.SelectedClicked | QAbstractItemView.AnyKeyPressed)
        self.points = sheet_points(lay)
        chosen = set(sheet.points)
        self.table.setRowCount(len(self.points))
        for i, p in enumerate(self.points):
            lt = latest.get(p.id)
            it = QTableWidgetItem(p.label)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            it.setCheckState(Qt.Checked if p.id in chosen else Qt.Unchecked)
            it.setData(Qt.UserRole, p.id)
            self.table.setItem(i, 0, it)
            name = QTableWidgetItem(lay.point_name(p.id))
            name.setToolTip("A name for this point on the sheet and the layout, e.g. after AOM, fiber in")
            self.table.setItem(i, 1, name)
            for j, v in ((2, format_power(lt[0].power_mw) if lt else "—"), (3, _when(lt[0].measured_at) if lt else "")):
                c = QTableWidgetItem(v)
                c.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if j == 2:
                    c.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, j, c)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(180, self.table.columnWidth(1)))
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        all_btn, none_btn = QPushButton("Select all"), QPushButton("None")
        all_btn.clicked.connect(lambda: self._check_all(True))
        none_btn.clicked.connect(lambda: self._check_all(False))
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Tick the points for the sheet; double-click a name to edit it."), 1)
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)

        self.include_log = QCheckBox("Include power log")
        self.include_log.setToolTip("Latest reading per point (power, meter, date, notes). Off: blank columns "
                                    "to fill in by hand.")
        self.include_log.setChecked(sheet.include_log)
        self.history = QSpinBox()
        self.history.setRange(1, 100)
        self.history.setValue(sheet.history)
        self.history.setPrefix("History: last ")
        self.history.setSuffix(" reading(s)")
        self.include_log.toggled.connect(self.history.setEnabled)
        self.history.setEnabled(sheet.include_log)
        self.include_picture = QCheckBox("Include layout picture")
        self.include_picture.setChecked(sheet.include_picture)
        opt_row = QHBoxLayout()
        opt_row.addWidget(self.include_log)
        opt_row.addWidget(self.history)
        opt_row.addSpacing(16)
        opt_row.addWidget(self.include_picture)
        opt_row.addStretch(1)

        copy = QPushButton("Copy for OneNote/Excel")
        copy.setToolTip("Puts the sheet on the clipboard: formatted (title, picture, table) and as plain "
                        "tab-separated text, so it pastes as a table in OneNote and as cells in Excel.")
        copy.clicked.connect(self.copy_sheet)
        copy_pic = QPushButton("Copy picture")
        copy_pic.setToolTip("Only the layout picture, for apps that drop the picture of the formatted copy")
        copy_pic.clicked.connect(self.copy_picture)
        prt = QPushButton("Print…")
        prt.clicked.connect(self.print_sheet)
        pdf = QPushButton("Save PDF…")
        pdf.clicked.connect(self.save_pdf)
        csv_btn = QPushButton("Save CSV/Excel…" if has_openpyxl() else "Save CSV…")
        csv_btn.clicked.connect(self.save_table)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        out_row = QHBoxLayout()
        for b in (copy, copy_pic, prt, pdf, csv_btn):
            out_row.addWidget(b)
        out_row.addStretch(1)
        out_row.addWidget(close)
        self.status = QLabel("" if logbook else "No power log yet (save the layout first): the sheet has no readings.")
        self.status.setStyleSheet("color:#555")

        v = QVBoxLayout(self)
        v.addLayout(sel_row)
        v.addWidget(self.table, 1)
        v.addLayout(opt_row)
        v.addLayout(out_row)
        v.addWidget(self.status)
        self.resize(720, 520)

    def _check_all(self, on: bool):
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    # ---- settings ----------------------------------------------------------------
    def sheet(self) -> LabSheet:
        """The settings as the dialog shows them now."""
        names = {pid: n for pid, n in self.lay.lab_sheet.names.items()}  # archived points keep theirs
        chosen = []
        for i, p in enumerate(self.points):
            n = self.table.item(i, 1).text().strip()
            if n:
                names[p.id] = n
            else:
                names.pop(p.id, None)
            if self.table.item(i, 0).checkState() == Qt.Checked:
                chosen.append(p.id)
        return replace(self.lay.lab_sheet, points=chosen, names=names, include_log=self.include_log.isChecked(),
                       history=self.history.value(), include_picture=self.include_picture.isChecked())

    def store(self) -> LabSheet:
        s = self.sheet()
        if s != self.lay.lab_sheet:
            self._store_fn(s)
        return s

    def done(self, r):
        self.store()
        super().done(r)

    # ---- content -----------------------------------------------------------------
    def title(self) -> str:
        return f"Lab sheet: {self.layout_name}"

    def subtitle(self) -> str:
        return f"Layout file {self.layout_name} · {datetime.now():%Y-%m-%d %H:%M}"

    def picture(self) -> QImage | None:
        if self._picture is None:
            self._picture = self._picture_fn()
        return self._picture

    def content(self):
        s = self.store()
        if not s.points:
            QMessageBox.information(self, "Lab sheet", "Tick at least one measurement point.")
            return None
        headers, rows = sheet_table(self.lay, self.logbook, s)
        return headers, rows, (self.picture() if s.include_picture else None)

    def copy_sheet(self):
        c = self.content()
        if c is None:
            return
        headers, rows, img = c
        QApplication.clipboard().setMimeData(clipboard_mime(self.title(), self.subtitle(), headers, rows, img))
        self.status.setText(f"Copied {len(rows)} row(s){' and the layout picture' if img else ''}. Paste into "
                            "OneNote or Excel (Ctrl+V). If OneNote leaves the picture out, use Copy picture.")

    def copy_picture(self):
        img = self.picture()
        if img is not None and not img.isNull():
            QApplication.clipboard().setImage(img)
            self.status.setText("Layout picture copied.")

    def document(self):
        c = self.content()
        if c is None:
            return None
        headers, rows, img = c
        return sheet_document(self.title(), self.subtitle(), headers, rows, img)

    def print_sheet(self):
        doc = self.document()
        if doc is None:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QDialog.Accepted:
            print_document(doc, printer)
            self.status.setText("Sent to the printer.")

    def _default_name(self, ext: str) -> str:
        stem = self.layout_name.rsplit(".", 1)[0] or "layout"
        return f"{stem}_labsheet_{datetime.now():%Y%m%d}.{ext}"

    def save_pdf(self):
        doc = self.document()
        if doc is None:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save lab sheet as PDF", self._default_name("pdf"), "PDF (*.pdf)")
        if p:
            write_pdf(doc, p)
            self.status.setText(f"Saved {p}")

    def save_table(self):
        c = self.content()
        if c is None:
            return
        headers, rows, _img = c
        filters = ("Excel (*.xlsx);;CSV (*.csv)" if has_openpyxl() else "CSV (*.csv)")
        p, chosen = QFileDialog.getSaveFileName(self, "Save lab sheet table",
                                                self._default_name("xlsx" if has_openpyxl() else "csv"), filters)
        if not p:
            return
        if p.lower().endswith(".xlsx") or (chosen.startswith("Excel") and not p.lower().endswith(".csv")):
            if not p.lower().endswith(".xlsx"):
                p += ".xlsx"
            write_xlsx(self.title(), self.subtitle(), headers, rows, p)
        else:
            write_csv(headers, rows, p)
        self.status.setText(f"Saved {p}")


__all__ = ["LabSheetDialog", "sheet_table", "sheet_html", "sheet_tsv", "clipboard_mime", "sheet_document",
           "write_pdf", "write_csv", "write_xlsx"]
