"""Layout data model: the single source of truth shared by the 2D editor,
the power logger and (later) the 3D generator.

Coordinates are millimetres on the table, origin at the table's top-left
corner, +x to the right, +y down (screen convention). Angles are degrees,
counter-clockwise as seen on screen, 0 = optic normal pointing +x.
"""

from __future__ import annotations

import json
import uuid
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORMAT_VERSION = 1


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# Board types: how the mounting holes are laid out. Any of them can also be
# irregular (Table.cutouts).
BOARD_STYLES: dict[str, tuple[str, dict]] = {
    # classic optical breadboard: 1/4-20 holes on a 1" grid
    "grid": ('1" grid, 1/4-20 (classic)',
             dict(hole_pitch=25.4, hole_offset=12.7, center_holes=False, hole_diameter=6.6)),
    # Olego board (Selim Jochim group, Heidelberg, PRA 2025): a 1/2" grid plus a
    # hole in the middle of every square, 8 holes per square inch, all the same size
    # (as drawn in olego_onDy2_board.SLDPRT: lattice from 12.7 mm off the edges, holes kept 6.25 mm clear)
    "olego": ("Olego, 8 holes per in², 4-40",
              dict(hole_pitch=12.7, hole_offset=12.7, center_holes=True, hole_diameter=2.8, edge_margin=6.25)),
    # PyOpticL baseplate (UMass ion-trap group, github.com/UMassIonTrappers/PyOpticL): a 1" thick
    # plate, the beam 1/2" above it, half-inch optics screwed straight in (8-32) or on printed
    # surface adapters sunk in pockets, nothing on a regular hole grid. Its 1" design grid starts
    # 1/2" in from the corner; the plate goes on the table by 1/4-20 counterbored holes on that grid.
    "pyopticl": ('PyOpticL ion-trap baseplate, ½" beam, drilled per part',
                 dict(hole_pitch=25.4, hole_offset=12.7, center_holes=False, hole_diameter=4.5, grid_holes=False)),
    # LightFlow Optics optical circuit board (QITI group, IQC Waterloo; github.com/OpenQuantumDesign/oqd-OCB):
    # a 1/2" aluminium board, every optic 1" above it on a machined pedestal, held by tapped 8-32 holes
    # and M2 dowel pins drilled per part; 1/4-20 clearance holes hold the board to the table.
    "lightflow": ('LightFlow optical circuit board, 1" beam, drilled per part',
                  dict(hole_pitch=25.4, hole_offset=12.7, center_holes=False, hole_diameter=4.4, grid_holes=False)),
    # a board drilled only where parts go, parts on ordinary posts
    "predrilled": ("Pre-drilled: holes only under the parts",
                   dict(hole_pitch=25.4, hole_offset=12.7, center_holes=False, hole_diameter=6.6)),
}
_STYLE_KEYS = {k for _label, params in BOARD_STYLES.values() for k in params}


@dataclass
class Table:
    name: str = "Breadboard"
    width: float = 609.6  # 24 in
    height: float = 457.2  # 18 in
    hole_pitch: float = 25.4
    hole_offset: float = 12.7  # first hole centre from the edge
    # irregular boards: rectangles [x, y, w, h] (mm) cut out of the board's outline
    cutouts: list = field(default_factory=list)
    center_holes: bool = False  # an extra hole in the middle of every grid square
    style: str = "grid"  # key of BOARD_STYLES
    hole_diameter: float = 6.6  # drawn size of every hole (mm)
    edge_margin: float = 0.0  # no hole centre closer than this to an edge or cut-out (mm)
    grid_holes: bool = True  # the grid points are tapped holes (False: a design grid only, holes drilled per part)

    def hole_ok(self, x: float, y: float) -> bool:
        """Is there a hole at this grid point (inside the board, clear of edges and cut-outs)?"""
        m = self.edge_margin
        if not (m <= x <= self.width - m and m <= y <= self.height - m):
            return False
        return not any(cx - m < x < cx + cw + m and cy - m < y < cy + ch + m for cx, cy, cw, ch in self.cutouts)

    def apply_style(self, style: str) -> None:
        self.style = style
        for k in _STYLE_KEYS:  # what the previous style set and this one doesn't goes back to its default
            setattr(self, k, Table.__dataclass_fields__[k].default)
        for k, v in BOARD_STYLES[style][1].items():
            setattr(self, k, v)

    @property
    def has_grid(self) -> bool:
        return self.style != "predrilled"

    def in_cutout(self, x: float, y: float) -> bool:
        return any(cx < x < cx + cw and cy < y < cy + ch for cx, cy, cw, ch in self.cutouts)

    def on_board(self, x: float, y: float) -> bool:
        return 0 <= x <= self.width and 0 <= y <= self.height and not self.in_cutout(x, y)

    def center_hole_ok(self, x: float, y: float) -> bool:
        """A centre hole sits in a grid square only when all four corner holes exist."""
        h = self.hole_pitch / 2
        return all(self.hole_ok(x + dx, y + dy) for dx in (-h, h) for dy in (-h, h))

    def columns(self) -> int:
        return int((self.width - self.edge_margin - self.hole_offset + 1e-6) // self.hole_pitch) + 1

    def rows(self) -> int:
        return int((self.height - self.edge_margin - self.hole_offset + 1e-6) // self.hole_pitch) + 1

    @staticmethod
    def column_name(i: int) -> str:
        """0 -> A, 25 -> Z, 26 -> AA (spreadsheet style)."""
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    def hole_at(self, x: float, y: float) -> tuple[str, float, float] | None:
        """Nearest hole as ("C7", dx, dy): column letter from the left edge, row
        number from the top edge, and how far (mm) the point sits from that hole.
        None if the point is off the board."""
        if not self.has_grid or not self.on_board(x, y):
            return None
        i = min(max(round((x - self.hole_offset) / self.hole_pitch), 0), self.columns() - 1)
        j = min(max(round((y - self.hole_offset) / self.hole_pitch), 0), self.rows() - 1)
        hx, hy = self.hole_offset + i * self.hole_pitch, self.hole_offset + j * self.hole_pitch
        return f"{self.column_name(i)}{j + 1}", x - hx, y - hy


@dataclass
class Component:
    id: str
    type: str
    x: float
    y: float
    angle: float = 0.0
    label: str = ""
    part_number: str = ""
    notes: str = ""
    sch_id: str = ""  # schematic element this part realises ("" = layout-only, legacy files)
    auto_angle: bool = True  # angle follows the beams (see orient.py); rotating by hand turns it off
    pinned: bool = False  # moved by hand; until any part is, the layout copies the schematic arrangement


@dataclass
class Beam:
    """A straight beam segment between two components (by persistent id)."""

    id: str
    source: str
    target: str
    color: str = "#b77fd0"
    wavelength_nm: float | None = None
    label: str = ""


# Fiber couplers: how far behind the coupler (mm, along -x of the part) the
# fiber's free end is drawn, (on the layout, in 3D). A measurement point on a
# fiber coupler sits there: the power coming out of the fiber.
FIBER_END = {"fiber_cage": (78.0, 112.0), "fiber": (74.0, 74.0)}


@dataclass
class MeasurementPoint:
    """A place on a beam where power / beam pictures are logged, or (part_id
    set, beam_id None) the output of a fiber coupler's fiber.

    The id is permanent: measurement records in the logbook refer to it, never
    to x/y. If its beam (or part) is deleted the point is archived and keeps its
    last position, so its history stays reachable.
    """

    id: str
    label: str
    beam_id: str | None
    t: float = 0.5  # fraction along the beam, source -> target
    archived: bool = False
    x: float = 0.0  # last known position (mm), kept for archived points
    y: float = 0.0
    notes: str = ""
    part_id: str | None = None  # a fiber coupler: the point is at its fiber's end


# ---- schematic layer ---------------------------------------------------------
# The schematic is the first, functional drawing (like a KiCad schematic): which
# optical elements exist and how light flows between them. Sizes, part numbers
# and exact positions do not matter there. The layout realises it: each layout
# component may point at one schematic element (Component.sch_id), and extra
# layout-only parts (steering mirrors, irises) may sit along a connection.

@dataclass
class SchElement:
    id: str
    kind: str  # key of SCH_KINDS
    x: float = 0.0  # free schematic units, not to scale
    y: float = 0.0
    angle: float = 0.0
    label: str = ""
    notes: str = ""
    part: str = ""  # layout type (symbols.SYMBOLS key); "" = the kind's default
    part_number: str = ""  # "" = the part's default part number
    auto_angle: bool = True

    def layout_type(self) -> str:
        return self.part if self.part in SCH_KINDS[self.kind][2] else SCH_KINDS[self.kind][2][0]


@dataclass
class SchLink:
    """An optical connection: light goes from source to target (element ids)."""

    id: str
    source: str
    target: str
    color: str = "#b77fd0"
    wavelength_nm: float | None = None
    label: str = ""


@dataclass
class Schematic:
    elements: dict[str, SchElement] = field(default_factory=dict)
    links: dict[str, SchLink] = field(default_factory=dict)

    def links_touching(self, eid: str) -> list[SchLink]:
        return [k for k in self.links.values() if eid in (k.source, k.target)]

    def next_label(self, kind: str) -> str:
        prefix = SCH_KINDS[kind][1]
        used = {e.label for e in self.elements.values()}
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"


# kind -> (display name, label prefix, layout types it can become; first is the default)
SCH_KINDS: dict[str, tuple[str, str, list[str]]] = {
    "laser": ("Laser / beam source", "LAS", ["laser", "beam_entry"]),
    "mirror": ("Mirror", "M", ["mirror_rd_1in", "mirror_1in", "mirror_rd_half_in", "mirror_half_in",
                               "mirror_newport_half", "mirror_polaris_half", "mirror_d"]),
    "lens": ("Lens", "L", ["lens_lmr1", "lens_1in", "lens_half_in"]),
    "hwp": ("Half-wave plate", "HWP", ["hwp", "hwp_half", "hwp_crm"]),
    "qwp": ("Quarter-wave plate", "QWP", ["qwp", "qwp_half", "qwp_crm"]),
    "pbs": ("PBS", "PBS", ["pbs_mounted", "pbs", "pbs_half"]),
    "bs": ("Beam splitter", "BS", ["bs"]),
    "aom": ("AOM", "AOM", ["aom"]),
    "shutter": ("Shutter", "SH", ["shutter"]),
    "fiber": ("Fiber coupler", "FC", ["fiber_cage", "fiber"]),
    "iris": ("Iris", "IR", ["iris"]),
    "photodiode": ("Photodiode", "PD", ["photodiode"]),
    "dump": ("Beam dump", "BD", ["dump"]),
}


def kind_of_type(layout_type: str) -> str | None:
    for kind, (_n, _p, types) in SCH_KINDS.items():
        if layout_type in types:
            return kind
    return None


@dataclass
class LabSheet:
    """What the printable lab sheet shows (see labsheet.py), kept with the
    layout so the same points come up checked next time."""

    points: list = field(default_factory=list)  # measurement point ids on the sheet
    names: dict = field(default_factory=dict)  # point id -> name, e.g. "after AOM"
    include_log: bool = True  # latest reading(s) per point; off: blank columns to fill in by hand
    history: int = 1  # readings per point
    include_picture: bool = True  # the 2D layout

    @classmethod
    def from_dict(cls, d: dict | None) -> "LabSheet":
        d = d or {}
        return cls(points=[str(p) for p in d.get("points", [])],
                   names={str(k): str(v) for k, v in d.get("names", {}).items() if str(v).strip()},
                   include_log=bool(d.get("include_log", True)),
                   history=max(1, int(d.get("history", 1))),
                   include_picture=bool(d.get("include_picture", True)))


@dataclass
class Layout:
    table: Table = field(default_factory=Table)
    components: dict[str, Component] = field(default_factory=dict)
    beams: dict[str, Beam] = field(default_factory=dict)
    points: dict[str, MeasurementPoint] = field(default_factory=dict)
    schematic: Schematic = field(default_factory=Schematic)
    lab_sheet: LabSheet = field(default_factory=LabSheet)

    def point_name(self, pid: str) -> str:
        """The name given to a measurement point on the lab sheet ("" if none)."""
        return self.lab_sheet.names.get(pid, "")

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": "optolayout",
            "version": FORMAT_VERSION,
            "table": asdict(self.table),
            "components": [asdict(c) for c in self.components.values()],
            "beams": [asdict(b) for b in self.beams.values()],
            "measurement_points": [asdict(p) for p in self.points.values()],
            "schematic": {
                "elements": [asdict(e) for e in self.schematic.elements.values()],
                "links": [asdict(k) for k in self.schematic.links.values()],
            },
            "lab_sheet": asdict(self.lab_sheet),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Layout":
        lay = cls(table=Table(**d.get("table", {})))
        for c in d.get("components", []):
            c = {"auto_angle": False, "pinned": True, **c}  # older files keep their hand-set placement
            comp = Component(**c)
            lay.components[comp.id] = comp
        for b in d.get("beams", []):
            beam = Beam(**b)
            lay.beams[beam.id] = beam
        for p in d.get("measurement_points", []):
            pt = MeasurementPoint(**p)
            lay.points[pt.id] = pt
        sch = d.get("schematic", {})
        for e in sch.get("elements", []):
            e = {"auto_angle": False, **e}
            el = SchElement(**e)
            lay.schematic.elements[el.id] = el
        for k in sch.get("links", []):
            link = SchLink(**k)
            lay.schematic.links[link.id] = link
        lay.lab_sheet = LabSheet.from_dict(d.get("lab_sheet"))
        return lay

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Layout":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # ---- helpers -------------------------------------------------------
    def beams_touching(self, comp_id: str) -> list[Beam]:
        return [b for b in self.beams.values() if comp_id in (b.source, b.target)]

    def beam_length(self, b: Beam) -> float:
        a, c = self.components.get(b.source), self.components.get(b.target)
        if a is None or c is None:
            return 0.0
        return ((c.x - a.x) ** 2 + (c.y - a.y) ** 2) ** 0.5

    def optical_path(self, start: str, end: str) -> tuple[float, list[str]] | None:
        """Shortest path along beams from part `start` to part `end`:
        (length in mm, part ids along the way). Beams are followed either way,
        so it works whichever of the two was clicked first."""
        import heapq
        adj: dict[str, list[tuple[str, float]]] = {}
        for b in self.beams.values():
            L = self.beam_length(b)
            adj.setdefault(b.source, []).append((b.target, L))
            adj.setdefault(b.target, []).append((b.source, L))
        dist, prev = {start: 0.0}, {}
        todo = [(0.0, start)]
        while todo:
            d, cur = heapq.heappop(todo)
            if cur == end:
                path = [end]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                return d, path[::-1]
            if d > dist.get(cur, float("inf")):
                continue
            for nxt, L in adj.get(cur, ()):
                if d + L < dist.get(nxt, float("inf")):
                    dist[nxt], prev[nxt] = d + L, cur
                    heapq.heappush(todo, (d + L, nxt))
        return None

    def points_on(self, beam_id: str) -> list[MeasurementPoint]:
        return [p for p in self.points.values() if p.beam_id == beam_id]

    def points_at_part(self, comp_id: str) -> list[MeasurementPoint]:
        return [p for p in self.points.values() if p.part_id == comp_id]

    def fiber_end(self, comp_id: str, in_3d: bool = False) -> tuple[float, float] | None:
        """Where a fiber coupler's fiber ends (layout x, y), or None for other parts."""
        c = self.components.get(comp_id)
        if c is None or c.type not in FIBER_END:
            return None
        d = FIBER_END[c.type][1 if in_3d else 0]
        a = math.radians(c.angle)
        return c.x - d * math.cos(a), c.y + d * math.sin(a)

    def coupling_efficiency(self, p: MeasurementPoint, latest: dict) -> float | None:
        """For a point at a fiber's end: its last power over the last power just
        before the coupler (the point on the incoming beam closest to it), or None."""
        if not p.part_id or not latest or p.id not in latest:
            return None
        before = [q for b in self.beams.values() if b.target == p.part_id
                  for q in self.points_on(b.id) if not q.archived and q.id in latest]
        if not before:
            return None
        q = max(before, key=lambda q: q.t)
        p_in = latest[q.id][0].power_mw
        return latest[p.id][0].power_mw / p_in if p_in else None

    def point_xy(self, p: MeasurementPoint) -> tuple[float, float]:
        """Current position of a point: on its beam (or at its fiber's end), or
        last known if archived."""
        if p.part_id:
            end = self.fiber_end(p.part_id)
            return end if end is not None else (p.x, p.y)
        b = self.beams.get(p.beam_id) if p.beam_id else None
        if b is None:
            return p.x, p.y
        a, c = self.components[b.source], self.components[b.target]
        return a.x + (c.x - a.x) * p.t, a.y + (c.y - a.y) * p.t

    def schematic_from_layout(self, spread: float = 1.6) -> None:
        """Build the schematic from an existing layout (files made before the
        schematic layer): one element per part, one connection per beam, with
        the same ids for beams and connections so measurement points stay put."""
        for c in self.components.values():
            kind = kind_of_type(c.type)
            if kind is None or c.sch_id:
                continue
            eid = f"s_{c.id}"
            self.schematic.elements[eid] = SchElement(
                id=eid, kind=kind, x=round(c.x * spread / 10) * 10, y=round(c.y * spread / 10) * 10,
                angle=c.angle, label=c.label or self.schematic.next_label(kind), notes=c.notes, part=c.type,
                part_number=c.part_number, auto_angle=c.auto_angle)
            c.sch_id = eid
        for b in self.beams.values():
            a, z = self.components.get(b.source), self.components.get(b.target)
            if a and z and a.sch_id and z.sch_id:
                self.schematic.links[b.id] = SchLink(id=b.id, source=a.sch_id, target=z.sch_id, color=b.color,
                                                     wavelength_nm=b.wavelength_nm, label=b.label)

    def component_for(self, eid: str) -> Component | None:
        """The layout part that realises schematic element eid, if placed."""
        for c in self.components.values():
            if c.sch_id == eid:
                return c
        return None

    def is_routed(self, link: SchLink) -> bool:
        """True if beams connect the two ends of a schematic link, possibly
        through layout-only parts (steering mirrors etc., no sch_id)."""
        a, b = self.component_for(link.source), self.component_for(link.target)
        if a is None or b is None:
            return False
        adj: dict[str, set[str]] = {}
        for bm in self.beams.values():
            adj.setdefault(bm.source, set()).add(bm.target)
            adj.setdefault(bm.target, set()).add(bm.source)
        seen, todo = {a.id}, [a.id]
        while todo:
            cur = todo.pop()
            for nxt in adj.get(cur, ()):
                if nxt == b.id:
                    return True
                if nxt in seen:
                    continue
                seen.add(nxt)
                c = self.components.get(nxt)
                if c is not None and (not c.sch_id or c.sch_id not in self.schematic.elements):
                    todo.append(nxt)  # pass through layout-only parts only
        return False

    def ratsnest(self) -> list[tuple[str, str]]:
        """(component id, component id) for schematic links not yet built with beams."""
        out = []
        for k in self.schematic.links.values():
            a, b = self.component_for(k.source), self.component_for(k.target)
            if a is not None and b is not None and not self.is_routed(k):
                out.append((a.id, b.id))
        return out

    def next_point_label(self) -> str:
        n = 1
        used = {p.label for p in self.points.values()}
        while f"P{n}" in used:
            n += 1
        return f"P{n}"


def wavelengths_in_use(lay: "Layout") -> list[tuple[str, str, int]]:
    """(colour, name, number of beam segments) per wavelength, shortest first.
    Beams without a wavelength are grouped by colour."""
    names = {color.lower(): name for name, (_wl, color) in WAVELENGTH_COLORS.items()}
    groups: dict = {}
    for b in lay.beams.values():
        key = b.wavelength_nm if b.wavelength_nm else b.color.lower()
        g = groups.setdefault(key, {"colors": {}, "n": 0})
        g["colors"][b.color] = g["colors"].get(b.color, 0) + 1
        g["n"] += 1
    out = []
    for key, g in groups.items():
        color = max(g["colors"], key=g["colors"].get)  # the colour most of its segments use
        if isinstance(key, float):
            out.append((key, color, f"{key:g} nm", g["n"]))
        else:
            out.append((1e9, color, names.get(key, "other"), g["n"]))
    return [(c, n, k) for _wl, c, n, k in sorted(out, key=lambda e: e[0])]


# The lab's wavelengths -> beam colour used in the drawing (the choices for new
# beams; a beam keeps the colour it was saved with).
WAVELENGTH_COLORS: dict[str, tuple[float | None, str]] = {
    "421 nm": (421.0, "#b77fd0"),  # violet
    "530 nm": (530.0, "#2e9e3e"),  # green
    "626 nm": (626.0, "#e8571e"),  # red-orange
    "741 nm": (741.0, "#b0122b"),  # deep red
    "1064 nm": (1064.0, "#6b2b2b"),  # infrared, drawn dark brown
    "Other": (None, "#1f6fd1"),
}
