# Adding an Olego pillar and its mount

On an Olego board, every mount stands on a pillar made for it. The pillar's square flange screws into the board's 4-40 holes. The mount lands on the pillar's **seat**. The seat is the wide lower step on top of the pillar. It is not the small raised step next to it, which only locates the mount.

The 3D tab, the overlap check and the bill of materials all build this stack from the files described below. With the pillars so far, the optics land at 50.8 mm (2") to within 0.05 mm.

## 1. The mount (vendor CAD)

1. Put the vendor STEP file (`.step` or `.stp`) in `component_library/step/`.
2. Find how it sits. Run `tools/simplify_cad.py` once and look at it, or load the raw file and look at the bounds and the bore.
   - Optic centre: the centre of the bore, at the mirror face or in the middle of the lens or plate.
   - Beam axis: along the bore.
   - Base face: the face with the tapped hole the mount is screwed down by.
3. Add an entry to `POSES` in `tools/simplify_cad.py`:
   - `origin`: the optic centre, in the file's coordinates.
   - `x`: the file direction the optic faces, or the beam direction for a lens or plate.
   - `z`: the file direction pointing up, away from the base face.

   Example (MDI-HS): `dict(origin=(25.44, 25.0, -15.8), x=(0, 0, -1), z=(0, 1, 0))`.
4. Run `py -3.13 tools/simplify_cad.py <file name without extension>`. It prints `base X mm below the optic`; that number is the mount's `base_height`.
5. In `optolayout/mounts3d.py`, edit two tables:
   - `MODELS`: add `"<part type>": Model3D("<file>", <base_height>, mirror_disc=… or glass_disc=…)`.
   - `MESH_FOOTPRINT`: add the mesh's x/y extent (`pv.read(mesh).bounds`). The overlap check uses it.
6. If the base face's tapped hole is not under the optic, add the offset to `MOUNT_BASE_OFFSET`. For example, the MDI-HS hole is 20.5 mm behind the mirror. Measure it as the centre of the mesh's bottom face, in the library frame (x along the beam, y to the left). The pillar is placed there.
7. To draw the mount in more than one colour, add a rule to `REGION_COLORS` (see the MDI-HS example).

## 2. The pillar

1. Put the pillar in `component_library/Olego_step/`.
   - SolidWorks `.sldprt`: run `py -3.13 tools/sldprt_to_step.py`. It uses the SolidWorks on this PC to save a `.step` next to each part.
   - An `.stl` also works, as the MDI-HS pillar shows.
2. Add the file to `PILLAR_UP` in `tools/simplify_cad.py`. Give the file axis that points from the flange up to the mount, for example `"+y"`.
3. Run `py -3.13 tools/simplify_cad.py <pillar name>`. It:
   - stands the pillar up, with the flange bottom at z = 0 and centred on the flange;
   - writes `component_library/mesh/Olego/<name>.ply`;
   - prints and saves to `mesh/Olego/pillars.json` the pillar's height, its **seat** and every flat step on top.

   The seat is the largest upward flat face in the top 15 mm. Check that it's the step the mount's body really lands on; if it isn't, edit `pillars.json`.
4. In `optolayout/mounts3d.py`, add `"<part type>": "<pillar name>"` to `OLEGO_PILLARS`.

## 3. Check the stack

- **Optic height:** it is the seat height plus the mount's `base_height`. This command prints it for every part type:

  ```bash
  py -3.13 -c "from optolayout.mounts3d import *; [print(t, optic_height(t, 'olego')) for t in OLEGO_PILLARS]"
  ```

  It should be about 50.8 mm.
- **Exceptions:** add these to `OLEGO_OPTIC_RULE`:
  - `("seat+", d)`: the optic is `d` above the seat. Used for a cube sitting directly in the seat.
  - `("fixed", h)`: the optic is at `h` regardless of the seat. Used for a mount whose tapped boss stands proud of its plate, like the CRM1T on the CP33 pillar, or for a part still drawn as a simple shape.
- **Look at it:** open a board in the 3D tab and zoom in on the part.

## Current pillars (2026-10-11)

| Pillar | Height | Seat | For | Optic |
|---|---|---|---|---|
| Olego_MDI_HS (STL) | 25.32 | 24.30 | Radiant Dyes MDI-HS | 50.80 |
| Olego_M05 | 39.60 | 38.10 | Newport M05 | 50.76 |
| Olego_M05_0deg | 39.60 | 38.10 | M05 sending the beam straight back | 50.76 |
| Olego_polaris_0.5inch_mirror | 39.37 | 38.10 | Thorlabs Polaris K05 | 50.80 |
| Olego_CP33 | 31.50 | 30.50 | CP33, CRM1T, cage fiber coupler | 50.82 |
| Olego_RSP05 | 37.85 | 36.80 | RSP05 | 50.78 |
| Olego_PBS_0.5in | 45.47 | 44.50 | 1/2" PBS cube | 50.85 |
| Olego_LMR1 | 29.90 | 27.90 | LMR1 | **50.00** |
| Olego_SR475 | 44.00 | 44.00 | SR475 shutter | **48.75** |
| PD36A2_mount | 30.80 | 25.80 | PDA36A2 (simple shape for now) | 50.80 (fixed) |

The two in bold don't reach 2" yet:
- **LMR1:** its base height of 22.1 mm may be measured to the wrong face.
- **SR475:** the 3 mm hole we took as the aperture is 4.75 mm above its base, which puts the beam 2 mm low. Check which way the shutter sits on its pillar, and where its aperture is.
