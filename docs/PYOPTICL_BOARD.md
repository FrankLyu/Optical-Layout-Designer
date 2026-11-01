# PyOpticL ion-trap baseplate

Board type `pyopticl` (File > Board > Holes: "PyOpticL ion-trap baseplate"). It follows the baseplates made with [PyOpticL](https://github.com/UMassIonTrappers/PyOpticL) (UMass ion-trap group): `PyOpticL/library/__init__.py` (Baseplate), `library/adapters.py` (Surface_Adapter) and `library/thorlabs.py` (mount positions), as of 2026-10.

## What PyOpticL does, and what the app takes from it

| PyOpticL | Here |
|---|---|
| Solid plate, 1" thick (its modules use `base_dz = 1 in`) | 3D plate 25.4 mm thick (`PYOPTICL_PLATE_T`) |
| Optical plane `optical_height = 0.5 in` above the plate top | every optic at 12.7 mm; the 3D tab's beam height jumps to 12.7 |
| No regular hole grid; each part's holes are drilled where it goes | no hole array; grey 8-32 holes under each part; the 1" design grid is drawn as faint crosses and used for snapping |
| Grid unit 1" with `grid_offset` 0.5 grid from the corner | `hole_pitch 25.4`, `hole_offset 12.7`; grid points named like holes (A1 …) |
| Polaris mounts (K05S1 …): one 8-32 from below, base 1/2" under the optic | screwed straight onto the plate (1 screw in the BOM) |
| RSP05 / RSP1 / PDA10A2: `Surface_Adapter` 10 mm high, two 8-32s 25 / 40 mm apart across the beam, sunk in a pocket (`drill()`, +2 mm) | green adapter block under the mount, its outline in 2D and in the overlap check, a dark pocket opening in 3D |
| Cube on `Surface_Adapter` (cube 1 mm deep in it, standing on the plate) | same, for `pbs_half`, `pbs`, `bs` |
| Mounts taller below the optic (KM05, KM100, HCA3 …): a pocket (`drill()`, bounding box + 5 mm) | dark pocket opening in 3D, "(pocket)" line in the BOM |
| HCA3 fiber port mount: three 8-32s, 12.7 mm apart | 3 screws |
| IDA12 on a `Slide_Adapter` | slide adapter + 1 screw in the BOM (not drawn in 3D) |
| Plate to the table: 1/4-20 counterbored `mount_holes` on grid points, chosen by hand | chosen automatically: the clear grid point nearest each corner, plus one per ~8" of long edge |

Demo-level: pocket depths and the plate itself are not milled in 3D (the pocket is a dark patch on the top face), and the mount base offsets come from this app's meshes, not PyOpticL's numbers, so sub-mm differences remain.

## Adding a part type

In `optolayout/mounts3d.py`: put it in `PYOPTICL_ADAPTERS` if PyOpticL stands it on a surface adapter (height, bolt spacing, minimum length, and `top` when the adapter stands on the plate rather than under the mount's base), or in `PYOPTICL_SCREWS` if it takes more than one screw.

Example: `py -3.13 examples/make_pyopticl_board.py` writes `examples/pyopticl_board.json`.
