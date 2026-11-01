---
name: plan-board-layout
description: Plan a new optics board from a spec (board size, laser head, number of AOM double passes and fiber couplers) and build it as an Optical Layout Designer layout, following Jiahao's Olego design rules. Ask the option questions first, then generate the layout with a script.
---

# Plan a new board from a spec

Use this when the user asks for a layout that doesn't exist yet. A typical request:

> "Plan a 16 x 32 in board with 5 AOM double passes and 8 fiber couplings. The laser head is 20 x 10 cm."

For a photo of a board that already exists, use `skills/photo-to-layout` instead.

The work has five steps:

1. Ask the option questions.
2. Draft the layout with the defaults while waiting for answers.
3. Rebuild it with the answers.
4. Check clearances.
5. Send a picture, and say plainly what doesn't fit.

Worked example: `examples/make_aom5_fc8.py` → `626nm_system/AOM5-FC8.json` (2026-10-28).

## 1. Ask first, as options

Send every question in one message as numbered multiple-choice. The user answers with letters, like "1c 2b 3b 4c…". Mark one default with ★ on each question, and say that skipped questions take the ★ default. These are the questions used so far. Add any the spec leaves open.

1. **Board type:** a) LightFlow (1" beam) b) 1" grid with posts c) Olego (2" beam, pillars)
2. **Wavelength / folder:** a) 421nm_system b) 626nm_system c) 741nm_system d) others
3. **Laser head placement:** a) along a short edge b) in a corner, beam along the long edge c) off the board, beam enters through an edge
4. **Fiber outputs:** a) all on the far short edge b) along one long edge c) wherever they fit
5. **AOMs:** a) the same model for all, +1 order double pass with lens + retro mirror (ask the cat's eye focal length) b) mixed models/orders, listed by the user
6. **Fibers per AOM:** a) one each, plus unshifted fibers b) some AOMs feed two fibers through a PBS c) the user lists the mapping
7. **Power splitting:** a) HWP + PBS before every AOM and fiber b) fixed splitters
8. **Extras (any):** a) isolator after the laser b) shutters on fiber paths c) power measurement points at the fibers d) pick-off to a wavemeter or lock
9. **Mounts:** a) the lab's LightFlow small mounts b) Polaris 1/2" c) Radiant Dyes MDI-HS

Ask too when 6b is chosen: which AOMs feed two fibers? This went unasked in the worked example, so it had to be guessed.

Jiahao's answers for AOM5-FC8 were: 1c, 2b, 3b, 4c, 5a with f = 150 mm, 6b, 7a, 8 none, 9b.

## 2. Jiahao's design rules (Olego, fiber-coupled AOM boards)

These come from Jiahao; they apply unless the user says otherwise.

- **Every fiber has two steering mirrors** (MA, then MB) of its own, right before the coupler.
  - MA → MB is **at least 10 cm**.
  - MB → coupler is **about 10–30 cm**.
  - Mirrors shared with another fiber don't count. Extra fold mirrors earlier in the path are fine.
- **Two waveplates before every fiber**, a QWP + HWP, for PM alignment. Put them between MB and the coupler.
- **A HWP + PBS before every AOM**, to set its power. On a distribution bus, the tap's HWP + PBS and the double pass's own HWPD + PBSD both count.
- **AOM double pass:** PBSD → AOM → cat's eye lens (f) → QWP → retro mirror at 2f from the AOM. The return leaves PBSD on the other port.
- **Two fibers from one AOM:** HWPS + PBSS on that AOM's output. Each of the two outputs then gets its own MA/MB walk.
- **Olego:** snap to the 1/4" half-grid (Q = 6.35 mm). Beam height is 2" (`OLEGO_BEAM_HEIGHT`). Every mount stands on its own pillar: see `docs/OLEGO_MATING.md`. Pillar flanges make footprints bigger than the bare mounts.

## 3. How much room things take

Measure before drawing. These numbers decided the worked example:

| Item | Size in plan (mm) | Notes |
|---|---|---|
| Polaris 1/2" mirror at 45° | reaches ~19 from its centre | A beam parallel to a mirror line needs ≥ 25 mm. Two mirrors whose backs face each other need ≥ 25 mm in both x and y. |
| fiber_cage coupler | 41 wide, 62 behind the front | Couplers in one column need ≥ 45 mm (7 Q) pitch. |
| RSP05 waveplate | 11 thick along the beam, 22 across | Keep ≥ 12 mm from the coupler front. |
| AOM housing | 25 along the beam, 66 across | Double-pass rows 57 mm apart need the AOMs staggered (here by 50.8 mm). |
| f = 150 mm double pass | about 360 mm, PBSD to retro mirror | Five of these take about 60 % of a 32" board's width. |
| Laser head | the app box is 16 x 12 cm | Keep the real footprint clear and say so. |

**Budget the fiber section first.**
- With couplers on one edge, every MB sits 100–300 mm from that edge, and each walk needs its own vertical line.
- On a 16 x 32 in board with five f = 150 double passes, that leaves a strip about 20 cm wide for 8 walks. It did not fit cleanly.
- If the budget is short, say so before drawing. Offer these relaxations:
  - a shorter cat's eye (f = 100 mm frees about 10 cm);
  - couplers on the table at the board edge, as on Dy1;
  - 7.5 cm from MB to the coupler;
  - fewer AOMs split to two fibers;
  - a bigger board.

## 4. Layout pattern that works

This is the shape used in AOM5-FC8:

- **Laser and bus:** the laser sits in the top-left corner. M1 turns its beam down a vertical **bus** of HWPB + PBSB taps. The last tap is a plain mirror (MBUS) that takes what is left.
- **Double-pass rows:** they run left from the bus with their retro mirrors at the left edge. Each output leaves PBSD downwards, through MOUT, along a **lane** to the right, and crosses the bus between two taps.
- **Fiber walks:**
  - On its lane, MA turns the beam up by ≥ 101.6 mm and MB turns it right to the coupler (a "shear").
  - Order the columns so that a lane never passes another walk's MA/MB within 25 mm. Crossing beams are fine as long as no part sits at the crossing.
- **Second fibers:** PBSS sends the second beam up, then either:
  - **bottom:** MA turns it right, MB turns it down to a coupler on the bottom edge (MB ≥ 101.6 mm above the coupler); or
  - **top:** fold F turns it left, MA turns it up, MB turns it left to a coupler in the free strip right of the laser.

## 5. Build it

Copy `examples/make_aom5_fc8.py`. Keep these parts of it:

- **The docstring:** the user's answers, the rules, the beam path in words, the stand-ins, and anything that was guessed.
- **Constants in half-grid steps.** The fiber section goes in `COL` / `SLOT` / `SPLITS` / `X_WP`, so it can be moved as a block.
- **`build()`:** returns `(parts, beams)`. Use the same part tuple as `photo-to-layout`. A double pass is drawn one way only: the chain ends at the retro mirror, and the return starts a new chain at PBSD.
- **`make_layout()` and `__main__`:** these save `<wavelength>_system/<name>.json`.

Run it with `py -3.13 examples/make_<name>.py`. Never hand-edit the json.

## 6. Check, then send

1. Run `py -3.13 tools/check_clearance.py examples/make_<name>.py`. It checks every mount against every beam, every other mount, and the board edge, with bare-mount footprints. A walk can't be judged by eye, so run this every time.
2. Render the 2D picture offscreen, using `export_scene` with `QT_QPA_FONTDIR=C:/Windows/Fonts`. Look at the app's red overlap boxes. They include the Olego pillars, so they are stricter than the tool.
3. If clashes remain, search for positions instead of moving parts by hand. For example, use simulated annealing over the `COL` / `SLOT` / `SPLITS` grid values, scored by the tool's issue count plus penalties for broken distance rules.
   - Run a few topologies (which AOMs split, top or bottom) in parallel.
   - Each search is slow, about 5–10 min, so tell the user that it's running.
4. Send the picture with:
   - the beam path in a few lines;
   - the guesses;
   - and, if it doesn't fit cleanly, what clashes and the relaxation options as a lettered list, with your pick.

## Lessons from AOM5-FC8

- The first draft from defaults was useful, but the user's answers changed almost everything: board, folder, mounts and lens. Keep draft code easy to re-parametrise.
- The two-mirror fiber rule came after the second draft and doubled the space the fibers needed. Ask about the fiber walk rules up front (step 2 lists them now).
- Hand placement at 19 mm (3 Q) spacing failed every time. Use 25.4 mm (4 Q) between parallel walk lines.
