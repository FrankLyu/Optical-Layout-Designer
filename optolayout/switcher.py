"""Toolbar drop-down listing the layouts (.json) in the current layout's
folder, to switch between them. Self-contained: the main window only adds
it to the toolbar and calls refresh() after opening or saving a file."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QComboBox

BROWSE = "Browse…"


def is_layout_file(p: Path) -> bool:
    """A layout saved by this app (not some other .json in the folder)."""
    try:
        if p.stat().st_size > 20_000_000:
            return False
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    return isinstance(d, dict) and (d.get("format") == "optolayout" or {"table", "components"} <= d.keys())


def layouts_in(folder: Path | None) -> list[Path]:
    if folder is None or not folder.is_dir():
        return []
    return sorted((p for p in folder.glob("*.json") if is_layout_file(p)), key=lambda p: p.name.lower())


class LayoutSwitcher(QComboBox):
    """current() gives the open layout's path (or None); folder() the folder to
    list when nothing is open; switch(path) opens a layout and returns False if
    the user cancelled; browse() shows the usual Open dialog."""

    def __init__(self, current, folder, switch, browse, parent=None):
        super().__init__(parent)
        self._current, self._folder, self._switch, self._browse = current, folder, switch, browse
        self.setMinimumContentsLength(16)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setToolTip("Layouts in this folder: pick one to switch to it")
        self.activated.connect(self._picked)
        self.refresh()

    def folder_shown(self) -> Path | None:
        cur = self._current()
        return cur.parent if cur else self._folder()

    def refresh(self) -> None:
        cur = self._current()
        self.blockSignals(True)
        self.clear()
        for p in layouts_in(self.folder_shown()):
            self.addItem(p.stem, str(p))
        if cur is None:
            self.insertItem(0, "untitled", None)
        elif self.findData(str(cur)) < 0:  # not saved there yet
            self.insertItem(0, cur.stem, str(cur))
        self.insertSeparator(self.count())
        self.addItem(BROWSE, BROWSE)
        self.setCurrentIndex(max(0, self.findData(str(cur)) if cur else 0))
        self.blockSignals(False)

    def showPopup(self) -> None:
        self.refresh()  # files added or removed since
        super().showPopup()

    def _picked(self, i: int) -> None:
        data = self.itemData(i)
        cur = self._current()
        if data == BROWSE:
            self.refresh()
            self._browse()
        elif data and (cur is None or Path(data) != cur):
            self._switch(Path(data))
        self.refresh()  # shows what is open now (the old one if cancelled)
