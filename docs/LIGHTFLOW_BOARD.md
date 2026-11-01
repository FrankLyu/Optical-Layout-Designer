# LightFlow optical circuit board

Board type `lightflow` (File > Board > Holes: "LightFlow optical circuit board"). It follows the optical circuit boards (OCBs) designed in LightFlow Optics by the QITI group (IQC Waterloo). The open designs are in [OpenQuantumDesign/oqd-OCB](https://github.com/OpenQuantumDesign/oqd-OCB). The numbers below come from that repository's LightFlow `.json` exports (`Optical Modules/json/OM_S_01.json`, `OM_MOD_01_Cooling.json`), its hole drawings (`Optical Modules/drawings/OM_S_01.pdf`) and its renderings, as of 2026-10.

## The convention

| LightFlow / OQD | Here |
|---|---|
| Every element: `beam_height` 25.4 mm | every optic at 25.4 mm; the 3D tab's beam height switches to 25.4 |
| Board 1/2" aluminium (table holes are 1/4-20 clearance, 12.7 mm deep, i.e. through) | 3D board 12.7 mm thick |
| Each mount on a machined pedestal (grey blocks in the renderings) | grey pedestal, the LightFlow element's footprint, from the board up to the mount's base (1" minus the mount's base height) |
| Pedestal held by tapped 8-32 holes, 6.25 mm deep (hole "A") | 8-32 holes drawn in 2D, counted in the BOM |
| Located by M2 dowel pins, 2.1 mm deep (hole "B") | 2 mm holes drawn in 2D, counted in the BOM |
| 1/4-20 tapped holes for big parts (laser, boards on boards) (hole "C") | not drawn (no part type uses them yet) |
| 1/4-20 clearance holes to the table (hole "E") | chosen automatically on the 1" grid, near each corner and every ~8" of long edge, clear of every part |

## Pedestals used (library frame: x along the beam, y across; holes from the optic)

Most pedestals are the lab's own, measured on 2026-10-19 from `component_library/lightflow small mount - new`. To measure them, the .SLDPRT files were exported to STEP with `tools/sldprt_to_step.py`, then each part's footprint, top face and vertical holes were read off. Parts the lab has no pedestal for use the LightFlow library element from the OQD boards.

| Part type | Pedestal | Footprint x × y (mm) | Top | 8-32 holes in the board | M2 dowels |
|---|---|---|---|---|---|
| `mirror_polaris_half` | lab `polarismount` | 10.2 × 25.0, centred on the K05S1's tapped hole (x −8.02) | 12.7 | (−8.02, 0), from under the board into the mount | (−8.02, ±5) |
| `mirror_newport_half` | lab `newport_M05` | 12 × 25, centred at x −9.4 | 12.7 | (−9.4, 0) | (−9.4, ±5) |
| `hwp_half`, `qwp_half` | lab `RSP05` | 10.2 × 36 | 11.43 | (−0.64, ±13), counterbored; the mount is held by a centre screw from below | – |
| `pbs_half` | lab `halfinchpbsmount` | 16 × 38 | 19.05 (cube seat) | (0, ±13.5), counterbored | (0, ±5) |
| `lens_1in`, `fiber_cage`, `hwp_crm`, `qwp_crm` | lab `cagemount` | 15 × 61 | 5.1 | (0, ±25.1), counterbored | (0, ±10), (5.45, ±10) |
| `iris` | lab `irismount`: a column with the IDA12 screwed on its side at beam height, plus a foot | 9.4 × 21.4, all on one side of the beam | 35.4 (column) | (−0.16, −6.33), slotted | (−0.15, −22.18), (−0.15, −16.28) |
| `shutter` | lab `SRSshutter.json` | 26 × 60 | 20.65 | (0, −20.05), (0, 29.95) | – |
| `aom` | lab `IntraactionATM.json` / `IntraactionAOM-ATM` | 53.4 × 50.7 | 12.9 | (±22.75, 0) | (0, 0) |
| `mirror_d` (new part: D-shaped 1" mirror in a DMM1) | lab `Left D-Shaped Mirror Mount`: the DMM1 on its own column and slotted foot, one CAD (`component_library/step/DMM1_lab.step`) | 11.7 × 35.2, column on the left of the beam | none (the column puts the mirror at 1") | (−4.48, 23.9), slotted | (−4.48, 13.95), (−4.48, 8.05) |
| `fiber` | OQD "Schafter Kirchhoff collimator Ver 2" | 40.2 × 42 | none | (−23.5, ±15) | (−23.5, ±5) |
| `photodiode` | OQD "1 inch photodiode" | 28.25 × 27 | 5.4 | (−21.7, ±6.35) | – |
| `dump` | OQD "Small Beam Block" | 12.5 × 11 | 10.4 | (−8.25, 0) | – |

In LightFlow's .json files, the origin's y fraction is counted from the +y side. Both `SRSshutter.json` and `IntraactionATM.json` confirm this: their holes only fall inside the footprint that way.

In 3D, the lab pedestals are drawn from their real shapes. The STEP exports are in `component_library/step/LightFlow/LF_*.step`, posed in `POSES` in `tools/simplify_cad.py` (the point under the optic on the board, x along the beam, z up). `py -3.13 tools/simplify_cad.py LF_<name>` turns them into meshes in `component_library/mesh/LightFlow/`. The overlap check and the 2D outline use the footprint rectangles above.

Lab parts not used yet:
- `RDMount_new` (Radiant Dyes, 11.4 mm): the app's Radiant Dyes part is the MDI-HS, which is already taller than 1".
- `planebeamsplitter`: there is no plate beam splitter part type.
- `GnHAOM`/`GnHAOMv2`, `ATMplate`, `insulationlayer`, `AllMount`.

Any other part gets a pedestal the size of its mount's footprint and one 8-32 under its base. A mount whose base is already 1" or more below its optic (KM100, RSP1, MDI-HS) screws straight onto the board.

## Known gaps (demo level)

- The lab's fiber couplers are the cage type (`fiber_cage`: asphere in a CP33, rods to the FC/APC plate), on the lab's `cagemount` under the front plate, as on the Olego board. The PAF2/HCA3 `fiber` part still uses the OQD collimator holder's holes and sits 1.6 mm into the board.
- The AOM spans its plate across the beam (50.7 mm) and is 25 mm along the beam and 25 mm tall (`LIGHTFLOW_BODY` in mounts3d.py); along-beam length and height are estimates.
- Which side of the beam the iris column goes on, and which way round the slotted dowels sit, are guesses; the parts are otherwise symmetric.

Example: `py -3.13 examples/make_lightflow_board.py` writes `examples/lightflow_board.json`.
