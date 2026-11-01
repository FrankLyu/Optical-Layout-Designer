# Next steps (written 2026-10-11)

These goals come from a hands-on review of the app after the UI rework. I opened `examples/demo_schematic.json` and `examples/demo_399nm.json`, took screenshots of both tabs at several zoom levels, and opened the parts table.

## Keep as is
- The schematic defines the parts; the layout only moves and rotates them.
- Live sync and cross-probing between the two tabs.
- Auto-aiming of mirrors, cubes and inline optics.
- The parts table (Ctrl+T).
- The append-only power logbook, tied to beam ids.

## Goal 1: Layout readability (do first)
1. **Measurement-point callouts**
   - Draw the callout box offset from the marker, with a thin line back to the marker.
   - Push the box automatically so it doesn't sit on parts, part labels or other callouts.
   - Scale with zoom within limits instead of staying a constant screen size. Today they cover parts when the board is fitted and turn into tiny boxes when zoomed in.
   - The A+/A− text-size setting still applies.
   - *Done when:* in the 399 nm demo fitted to the window, no callout overlaps a part or label (P1/HWP1, P3/"+80 MHz", P2/P4/MOT labels).
2. **Beams**
   - Make them thicker and draw them in the wavelength colour at full strength.
   - Add direction arrows, as in the schematic.
   - They must stay visible over the hole pattern.
3. **Part labels**
   - Make them bigger at the fitted view (today they are about 8 px on a 36"x24" board).
   - Place them automatically so they don't collide; for example, "HWP1 PBS1 HWP2" currently run together.

## Goal 2: Schematic readability
- Make the part-name line under each symbol readable. It is grey and about 5 px today.
- Stop labels from overlapping the symbol's marks (HWP2's label currently sits on its λ/2 mark).
- When a file opens, fit **both** tabs. The schematic can open zoomed far out in one corner.

## Goal 3: Part numbers and bill of materials
- Picking a part fills in a default part number (for example, Mirror 1" Thorlabs → KM100). You can still override it.
- Add a BOM view or export that groups parts by part number with quantities. It should also list the posts, post holders and forks implied by the 3D generator.

## Goal 4: Measuring on the table
- Hole coordinates along the breadboard edges (columns A, B, C…, rows 1, 2, 3…), with each part's hole shown in Properties.
- A ruler tool: drag to measure a distance in mm and inches.
- Beam-segment lengths and the total optical path between two selected parts, needed for spacing lenses by focal length and matching path lengths.

## Goal 5: Panels and toolbar
- Each tab shows only its own tools; hide the rest instead of greying them out.
- When nothing is selected, use the Properties panel for something useful, such as a board summary or a legend.
- Power log: fill in the Status column or remove it, and fit the column widths.
- Add a wavelength legend and test the colours with a board that mixes wavelengths.

## Later
- **Beam-path check (DRC):** flag a beam that doesn't actually leave a mirror or cube along the drawn direction, or that is clipped by a part (listed in `docs/UI_NOTES.md` as not done). This leads into Milestone 3 (ray tracing).
- **3D in the editor:** today 3D is only the command-line `tools/render3d.py`. Add *File → Render 3D…* (it takes about 1 min) and *File → Export STEP*, run in the background, with the image shown when done.
  - The camera fits the whole board instead of a close-up of one corner.
  - Add 3D models for the PBS, AOM, lens, laser box and beam dump. These are skipped today, so the 399 nm render shows beams passing through empty space.
- **More parts:** ND filter, EOM, cylindrical lens, periscope, camera, telescope pair, and fiber couplers with a drawn fiber.
- **Not done yet from `docs/UI_NOTES.md`:**
  - parts follow the cursor after you add them;
  - a move reference point at the post hole;
  - pack the selected parts together.

## Suggested order
Goals 1 and 2 as one visual pass, then Goal 3, then Goal 4, then Goal 5.
