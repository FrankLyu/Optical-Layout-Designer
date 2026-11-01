---
name: photo-to-layout
description: Turn a top-down photo of a real optics board into an Optical Layout Designer layout (parts placed on the board, beams routed in the schematic), in two rounds with the user's beam sketch.
---

# Photo of a board → layout

Use this when the user gives a photo of a real breadboard or optical circuit
board and wants it in the app as a layout `.json`.

The work goes in **two rounds**:

- **Round 1:** place the parts from the photo.
- **Round 2:** route the beams from the user's sketch and words.

Don't try to get the beams right from the photo alone. A photo shows mounts, not
light. In the worked example below, round 1 placed the parts well, but the
routing was only about 60 % right. Round 2 reached about 99 %.

Everything is built by a generator script, `examples/make_<name>.py`, that writes
`<wavelength>_system/<name>.json`. A script can be re-run after every
correction, and it records how the layout was derived.

## What the app expects (read before starting)

- **The schematic owns parts and beams; the layout only owns positions.**
  - Each part is a `SchElement` in `lay.schematic` and a `Component` in
    `lay.components`, linked by `sch_id`.
  - Each beam is a `SchLink` between schematic element ids.
  - The layout's beams are synced from the links when the file opens.
- **Coordinates:**
  - mm from the board's top-left corner, +x right, +y down.
  - Angles in degrees, counter-clockwise on screen.
  - `auto_angle=True` lets linked parts aim themselves from their beams.
- **Part types** are the keys of `optolayout/symbols.py` `SYMBOLS`. The schematic
  kinds and their allowed types are in `optolayout/model.py` `SCH_KINDS`.
- **Board types** are in `model.BOARD_STYLES`: `grid`, `olego`, `pyopticl`,
  `lightflow`, `predrilled`. For LightFlow pedestals and holes, see
  `docs/LIGHTFLOW_BOARD.md`. Use `Table(...).apply_style(style)`.
- **Default wavelengths and colours** are in `model.WAVELENGTH_COLORS`:
  421, 530, 626, 741 and 1064 nm.

## Round 1: the photo → parts on the board

1. **Board facts.** Ask, or measure from the photo:
   - **Board type:** the hole pattern gives it away. A 1" grid of 1/4-20 holes is
     `grid`. A 1/2" grid plus centre holes is `olego`. A plate with pedestals and
     few holes is `lightflow` or `pyopticl`.
   - **Size:** count the holes along two edges; size = holes × pitch. If the
     board's edge holes aren't visible, say the size is an estimate.
   - **Wavelength and power:** these decide the output folder and the beam colour.
2. **Map the photo to the board.**
   - Find the four board corners in the photo.
   - Fit a perspective (homography) from the photo to the board's mm.
   - Check the fit against hole rows: a row of holes must come out evenly
     spaced at the pitch.
   - Read every position through that fit, never straight from photo pixels.
3. **Inventory the parts by their top-down look.** For each one, note the part,
   its mount, its pedestal, which way it faces, and anything odd. The app types
   used so far:

   | Looks like | Part type | Notes |
   |---|---|---|
   | Small black kinematic mount, 1/2" optic | `mirror_polaris_half` | Polaris K05S1 |
   | Red mount (Radiant Dyes MDI-HS) | `mirror_newport_half` for now | say "drawn as M05" in notes |
   | Newport M05 / Thorlabs KM05 | `mirror_newport_half` / `mirror_half_in` | |
   | KM100 1" mirror | `mirror_1in` | |
   | D-shaped mirror (DMM1), half-moon optic | `mirror_d` | pick-off mirror |
   | Rotation mount with a waveplate | `hwp_half` / `qwp_half` (RSP05), `hwp_crm` (CRM1T cage) | |
   | Cube in a clamp | `pbs_half` (1/2"), `pbs_mounted` | |
   | Plate beam splitter | `pbs_half` | there is no plate type yet: say so in notes |
   | Blue IntraAction box with an SMA cable | `aom` | write the model (ATM-200/350/400) in notes |
   | Cage plates on rods with a lens | `lens_1in` (cage), `lens_lmr1`, `lens_half_in` | a telescope is two lenses |
   | Iris on a column | `iris` | |
   | SR475 shutter (black box with a slot) | `shutter` | |
   | Fiber coupler (cage, FC plate, fiber leaving) | `fiber_cage`, or `fiber` (PAF2) | often on the table at the edge |
   | Beam block | `dump` | |
   | Laser, or the beam coming in from off the board | `laser` / `beam_entry` at the board edge | |

   If a mount isn't in the table, ask. Don't invent a part type: use the closest
   one and say so in `notes`.
4. **Positions on beam lines.**
   - Read the centre of each optic, not of its post or pedestal.
   - Parts that sit on one straight beam must share exactly one y (horizontal
     run) or one x (vertical run). Name those lines as constants (`Y1`, `X_UP`, …)
     and use them for every part on the line.
   - Beams look straight in reality; small reading errors must not turn them into
     diagonals.
   - On grid boards, snap to holes. On drilled-per-part boards (LightFlow), keep
     the photo value, rounded to 0.1 mm.
5. **Names.** Number each kind in the order the light meets it: M1…, HWP1…,
   PBS1…, L1…, AOM1…, IR1…, SH1…, FC1…, DM1…. Put the real model or setting in
   `notes`.
6. **Draft beams.** Join only the parts whose order is obvious, and keep the draft
   in the script. Then render the 2D layout: open the app, or use
   `export_scene(scene, "draft.png")`, as in `tests/test_smoke.py`.
7. **Ask for round 2.** Send the 2D picture and ask the user to:
   - draw the real beam paths in red over it (any paint program);
   - describe in words what the light does: where it enters, any double passes
     (which AOM, which retro mirror), where each split goes, which fiber coupler
     gets which beam, which AOM order (0th or 1st) goes where, and any pick-off
     mirrors.
   - Tell them to ignore the black blocks: those are label placeholders in the
     exported picture, not parts.

## Round 2: sketch + words → beams

1. **Read the words first; they win over the sketch.** The sketch shows where
   lines go. The words say what they mean: "double pass", "0th order", "picked
   off by a D mirror". Write the words as a beam-path summary in the script's
   docstring.
2. **Trace each red line.** List the parts it touches in order. Every corner in a
   red line is a mirror, or a PBS reflection. If a corner has no part, ask; it is
   often a mount you missed or mis-placed.
3. **Move turning parts onto the lines** so every segment is horizontal or
   vertical, as in the photo. Usually only mirrors move; most other parts were
   already on their lines.
4. **Write the chains** as `BEAMS`, a list of tuples of element ids. One tuple is
   one straight-through path. These conventions keep the schematic readable:
   - **Double pass:** drawn one way only. The chain ends at the retro mirror, and
     the returning light starts a new chain at the PBS that sends it on, e.g.
     `("pbs1", "m3", ...)`.
   - **Split (PBS or plate):** one chain carries on through the splitter's
     transmitted output, and a new chain starts at the splitter for the other
     output.
   - **0th-order pick-off:** a new chain starts at the part just before the
     pick-off (e.g. `("l3", "dm1", ...)`), so it branches off the double pass.
   - **Fiber couplers on the table at the edge:** draw them just inside the
     board, and say "on the table at the edge" in notes.
5. **Angles.** Parts in a chain get `auto_angle=True`. Ends that aren't linked
   (beam entry, retro mirrors, fiber couplers) get an explicit angle facing their
   beam: 0 is +x, 90 is up the screen, 180 is −x, 270 is down.
6. **Colour.** Give every link the wavelength's colour and `wavelength_nm` from
   `WAVELENGTH_COLORS`.

## The generator script

Copy `examples/make_dy1_lowpower.py` and keep its shape:

- **Docstring:** where the photo came from and its date, how positions were
  measured, the beam path in words, and the stand-ins used ("red mounts drawn as
  M05").
- **Beam-line constants** (mm).
- **`PARTS`:** `id: (kind, part type, label, x, y, angle, notes)`.
- **`BEAMS`:** the chains.
- **Loops** that make a `SchElement` plus a pinned `Component` per part, and a
  `SchLink` per neighbouring pair in a chain. Schematic positions are the board
  positions × 1.6, rounded to 10.
- **`__main__`:** saves to `<wavelength>_system/<name>.json`.

Run it with `py -3.13 examples/make_<name>.py`. Never hand-edit the `.json` and
then re-run the script: the script overwrites the file.

## Check before sending

- **Links:** open it with `py -3.13 run.py <wavelength>_system/<name>.json`.
  Schematic tab: no dashed "not yet routed" links, and every part is connected
  unless it really is spare.
- **Layout tab:**
  - Layout > Show overlapping parts finds nothing, or only real tight spots.
  - Every beam segment is straight along its line.
  - The light enters where the user said.
- **3D tab:** mounts stand on their pedestals or posts, beams at the board's beam
  height, nothing floating.
- **Words against links:** walk the user's description and point to each link
  that realises it. Anything you can't point to is a mistake.
- **Report:**
  - Send the 2D screenshot, plus 3D if useful.
  - Send the beam path in words.
  - List the guesses: stand-in part types, estimated board size, parts you
    couldn't identify.
  - Ask what's still wrong, then iterate.

## Pitfalls seen so far

- **Routing from the photo alone:** in round 1 of the example, it joined parts
  that look aligned but aren't on one beam, and missed both double passes and the
  0th-order branch. That's why routing waits for the user's sketch.
- **Double passes look like dead ends:** a retro mirror and its PBS look like
  parts on one line. The light comes back and leaves the PBS on a *different*
  port.
- **Pick-off mirrors are easy to miss:** a D-shaped mirror next to a beam takes
  one AOM order. It needs its own chain.
- **Fiber couplers off the board:** couplers often stand on the table at the
  board's edge. Place them just inside the edge, or they end up "waiting below
  the board".
- **Plate beam splitters and Radiant Dyes mounts** have no exact part type.
  Use the stand-ins and say so in notes; don't silently pick another part.
- **Black blocks in exported pictures** are label placeholders. Neither you nor
  the user should read them as parts.
- **Perspective:** pixels near the far edge of an oblique photo are compressed.
  Without the corner fit, those parts end up too close together.

## Questions to ask the user (round 1, if the photo doesn't say)

1. Board type and size (or confirm your hole count).
2. Wavelength, power, and where the beam comes onto the board.
3. Which mounts are which brand, for any you can't tell (red mounts, plate vs cube
   splitters).
4. AOM models and what each one does (single or double pass).
5. Where the fibers go (which coupler feeds what), if known.

## Example: Dy1-lowpower (421 nm LightFlow board, 2026-10-19)

Files:
- `examples/make_dy1_lowpower.py`: the generator, with the full beam path in its
  docstring.
- `421nm_system/Dy1-lowpower.json`: the output.
- `skills/photo-to-layout/example/rounds_comparison.png`: the user's comparison
  sheet (photo, round 1, red sketch, words, round 2).
- `skills/photo-to-layout/example/dy1_lowpower_2d.png`: the final 2D layout.
- `skills/photo-to-layout/example/dy1_lowpower_3d.png`: the final 3D view.

**Round 1.**
- **Input:** a top-down photo of the LightFlow board, with Polaris and red
  Radiant Dyes mirrors, RSP05 waveplates, 1/2" PBS cubes and plate splitters,
  three IntraAction AOMs, a cage telescope, an SR475 shutter and five fiber
  couplers on the top and right edges.
- **Done:**
  - board type `lightflow`;
  - size about 17 × 16 in from the hole count, an estimate;
  - corner fit;
  - parts placed on shared beam lines;
  - draft beams.
- **Result:** part positions mostly right; routing about 60 % right.

**Round 2.**
- **Input:** the user drew the real beams in red over the round-1 screenshot, and
  wrote:

  > The picture is what it looks like in reality. It goes from the left. Then goes
  > through a Double pass. Then some light gets split into 2 FC. Other light goes
  > through a 2nd DP (left up AOM) and split into another 2 FC. The right edge up
  > most FC is the light the 0th order of the 2nd AOM. It gets picked from a D
  > shape mirror and goes through the 3rd AOM.

- **Done:**
  - Read the words as five facts: entry from the left; double pass 1 (AOM1, retro
    M2); split to two FCs (PBS3 → FC4 and FC5); double pass 2 (upper-left AOM2,
    retro M9) then a split to two FCs (PBS5 → FC1 and FC2); AOM2's 0th order
    picked off by DM1 through AOM3 to the top-right coupler FC3.
  - Traced the red lines to find the turning mirrors.
  - Moved those mirrors onto the beam lines.
  - Wrote seven chains, using the conventions above.
- **Result:** about 99 % right.
