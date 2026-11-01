"""Re-save SolidWorks parts as STEP using the SolidWorks installed on this PC.

    py -3.13 tools/sldprt_to_step.py [folder]

Converts every *.sldprt in the folder (default: component_library/Olego_step)
to a .step file next to it, skipping parts that already have one. SolidWorks
runs in the background and is closed again if this script started it.
Needs pywin32 (pip install pywin32); PowerShell can't drive SolidWorks'
COM interface, so this replaces tools/sldprt_to_step.ps1.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import VARIANT

ROOT = Path(__file__).resolve().parents[1]
SW_DOC_PART = 1
SW_OPEN_SILENT = 1


def running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe"], capture_output=True, text=True).stdout
    return "SLDWORKS.exe" in out


def connect():
    """SolidWorks, once it answers: just after it starts, calls fail with "remote procedure call failed"."""
    sw = win32com.client.Dispatch("SldWorks.Application")
    for _ in range(90):
        try:
            sw.RevisionNumber
            break
        except pythoncom.com_error:
            time.sleep(2)
    sw.Visible = False
    return sw


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "component_library" / "Olego_step"
    parts = sorted(p for p in folder.rglob("*") if p.suffix.lower() == ".sldprt" and not p.name.startswith("~$"))
    if not parts:
        print("No .sldprt files in", folder)
        return
    was_running = running()
    sw = connect()
    err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    for p in parts:
        out = p.with_suffix(".step")
        if out.exists():
            print(f"skip  {p.name} (STEP already there)")
            continue
        try:
            doc = sw.OpenDoc6(str(p), SW_DOC_PART, SW_OPEN_SILENT, "", err, warn)
            if doc is None:
                print(f"FAIL  {p.name}: SolidWorks could not open it (error {err.value})")
                continue
            ok = doc.SaveAs(str(out))  # the .step extension picks the STEP exporter
            title = doc.GetTitle
            sw.CloseDoc(title() if callable(title) else title)
        except pythoncom.com_error as e:  # SolidWorks fell over on this part: start it again for the next one
            print(f"FAIL  {p.name}: {e.args[1]}")
            sw = connect()
            continue
        print(f"ok    {p.name} -> {out.name}" if ok and out.exists() else f"FAIL  {p.name}: export wrote nothing")
    if not was_running:
        sw.ExitApp()


if __name__ == "__main__":
    main()
