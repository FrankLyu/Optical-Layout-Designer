# UI research notes (2026-10-10)

We looked at KiCad (schematic and PCB editors), PyOpticL, gtrace, Zemax OpticStudio, Franzen's ComponentLibrary, Ray Optics Simulation, and Figma/draw.io conventions.

**Adopted:**

| Pattern | From | Here |
|---|---|---|
| Schematic drives the board | KiCad F8 | Live sync instead of an F8 step: the layout always matches the schematic |
| Staging area for new parts | KiCad users' top complaint is new parts landing off the board | Strip under the table, labelled, with a status-bar hint |
| Two-way cross-probing | KiCad | Selection mirrors between tabs; double-click jumps to the schematic; centres on the part |
| Bulk field editor | KiCad Symbol Fields Table | Parts table (Ctrl+T) with drop-downs, undo and CSV export |
| Mirror bisects its beams | Not a GUI feature anywhere we found; PyOpticL/gtrace compute it in code | Auto-aim for mirrors, inline optics, end points and cubes; manual rotate overrides it; A restores it |
| Insert an element into a beam | OpticStudio "Add Fold Mirror", PyOpticL `place_element_along_beam` | Place a symbol on a schematic beam to split it; the upstream half keeps the beam id so measurement points stay |
| Arrow-key nudge by grid, fine modifier | KiCad, Figma | Arrows = 1 hole, Shift = 1 mm (schematic: 1 / 5 grid) |
| Skip snapping with a modifier | draw.io (Alt) | Alt-drag in the layout |
| Duplicate | Figma/draw.io Ctrl+D | Ctrl+D in the schematic; the layout follows. The layout never creates parts on its own, so the two can't drift apart |
| Courtyard collision highlight | KiCad | Red dashed outline on overlapping parts; Layout → Show overlapping parts |
| Labels with a constant screen size | Qt `ItemIgnoresTransformations`; KiCad designators | Measurement-point labels; adjustable with Ctrl+= / Ctrl+- |
| Zoom to selection | Common CAD | Z |

**Not done yet:**
- Parts that follow the cursor after F8.
- Move vs. drag distinction: beams always stay attached here.
- A move reference point at the post hole.
- Pack-selection.
- A DRC for clipped beams.
