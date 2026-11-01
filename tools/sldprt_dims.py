"""Read the named dimensions of a SolidWorks part without SolidWorks.

    py -3.13 tools/sldprt_dims.py part.SLDPRT [preview.png]

SolidWorks 2015+ files are a chain of deflate-compressed sections. One of them
holds the annotation data, with every driving dimension stored by name
(D1@Sketch1, D2@Fill Pattern1, ...) followed by its value as a big-endian
double after a "value" key, lengths in metres. This prints them in mm and
inches, and can save the file's preview picture. Read-only: nothing is
written to the part.
"""

from __future__ import annotations

import re
import struct
import sys
import zlib
from pathlib import Path


def sections(data: bytes, min_size: int = 200):
    """(offset, decompressed bytes) of every deflate section in the file."""
    i = 0
    while i < len(data) - 2:
        d = zlib.decompressobj(-15)
        try:
            out = d.decompress(data[i:i + 1_000_000])
            if d.eof and len(out) >= min_size:
                yield i, out
                i += len(data[i:i + 1_000_000]) - len(d.unused_data)
                continue
        except zlib.error:
            pass
        i += 1


def dimensions(data: bytes) -> dict[str, float]:
    dims: dict[str, float] = {}
    for _off, out in sections(data):
        if b"DimSemData" not in out:
            continue
        for m in re.finditer(rb"(D\d+@[A-Za-z0-9 _\-]+?\d+)(?=[^A-Za-z0-9 _\-])", out):
            seg = out[m.end():m.end() + 400]
            j = seg.find(b"value")
            if j >= 0 and seg[j + 5] == 0xCB:  # msgpack float64
                dims[m.group(1).decode()] = struct.unpack(">d", seg[j + 6:j + 14])[0]
    return dims


def preview(data: bytes) -> bytes | None:
    for _off, out in sections(data, 1000):
        k = out.find(b"\x89PNG")
        if k >= 0:
            return out[k:]
    return None


def main():
    path = Path(sys.argv[1])
    data = path.read_bytes()
    dims = dimensions(data)
    if not dims:
        print("No dimension data found (older file format, or saved without annotations).")
    for name in sorted(dims, key=lambda n: (n.split("@")[1], n)):
        v = dims[name]
        if abs(v) < 2:  # lengths (m) and angles (rad) are small; counts are whole numbers
            print(f"{name:24s} {v * 1000:10.3f} mm  {v * 1000 / 25.4:8.4f} in   (or {v:.6f} rad)")
        else:
            print(f"{name:24s} {v:10g}")
    if len(sys.argv) > 2:
        png = preview(data)
        if png:
            Path(sys.argv[2]).write_bytes(png)
            print("preview saved to", sys.argv[2])


if __name__ == "__main__":
    main()
