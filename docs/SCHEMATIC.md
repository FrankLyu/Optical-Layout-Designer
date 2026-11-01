# Schematic layer

The schematic defines the system: parts, part numbers and beams. The layout places it on the table, and that is the only thing you do there. See the README's *How it works*, *Schematic* and *Layout* sections for the controls.

## Design notes
- **Live, not F8.** Earlier versions needed an "Update layout" step. The layout now follows every schematic edit straight away. That follow-up is derived state, so it is not on the undo stack. Undoing a schematic edit re-syncs the layout, and a deleted part comes back where it was.
- **Beam ids = connection ids.** A schematic beam and its layout beam share one id, so measurement points and their logbook history stay attached. When a beam disappears, its points are archived and keep their beam id. If the beam comes back, for example on undo, the points return with it.
- **The layout owns placement, the schematic owns identity.** The layout stores x, y, angle, "aim automatically" and "pinned" (moved by hand). Everything else comes from the schematic.
- **Older files:** a layout without a schematic gets one on open. Each part becomes an element and each beam becomes a connection with the same id. Parts keep their hand-set angles (auto-aim off) and their positions.

## File format
`"schematic": {"elements": [...], "links": [...]}`.
- Element fields: `kind`, `x`, `y`, `angle`, `label`, `notes`, `part` (layout type, "" = default), `part_number` ("" = default) and `auto_angle`.
- Layout components add `sch_id`, `auto_angle` and `pinned`.
