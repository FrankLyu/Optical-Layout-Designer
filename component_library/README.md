# Component library

`mounts.json` lists the mounts used in 3D, with each one's product page, size and optic height. The 3D view reads the light meshes in `mesh/`, which come with this repository, so it shows the real mounts without any download. The full STEP files aren't included. A part with no mesh is drawn as a simple shape, and the status line in the 3D tab says which models are missing.

## Add a new part from a STEP file
A part has two halves that you add separately: a 2D drawing for the schematic and layout, and a 3D model made from the vendor's STEP file. The 2D drawing is drawn by hand. It isn't made from the STEP file.

1. **Get the STEP file.** Download it from the vendor's page (on Thorlabs pages, look under the CAD tab) and save it in `component_library/step/`, for example `component_library/step/KM200.step`. The file name without its extension is the name the rest of these steps use.
2. **Line it up.** Put the model in the library frame (see [Line a model up](#line-a-model-up)). Vendor files usually need a `POSES` entry in `tools/simplify_cad.py`.
3. **Make the mesh.** This needs `pip install cadquery-ocp pyvista`:
   ```
   python tools/simplify_cad.py KM200
   ```
   It writes `component_library/mesh/KM200.ply`, which is what the 3D view reads. It also prints `base … mm below the optic`, the optic height you need in step 5. If that height or the model's shape looks wrong in the 3D view, fix the pose and run it again.
4. **Draw the 2D symbol.** In `optolayout/symbols.py`, write a draw function and `register()` it with a new type key, a name, a default part number and a toolbox group:
   ```python
   register("mirror_km200", 'Mirror 2" (Thorlabs)', _tl_mirror_2in, "KM200", "Mirrors")
   ```
   Draw it in the part's own frame, in mm: the optical point (mirror face, lens centre) at the origin, the beam along +x and the mount behind it at -x. Copying a similar existing symbol is the quickest start. The part then shows up in the toolbox.
5. **Link the type to the model.** In `optolayout/mounts3d.py`, add the type to `MODELS` with the STEP file name and the optic height from step 3:
   ```python
   "mirror_km200": Model3D("KM200.step", 38.10, mirror_disc=50.8),
   ```
   `mirror_disc` or `glass_disc` adds the optic itself, and `extras` lists adapters for the bill of materials.
6. **Give it its real footprint.** Add the mesh's top-down extent to `MESH_FOOTPRINT` in the same file. The overlap check and the adapter or pedestal sizing use it. Without it, the overlap check uses the 2D drawing, which is drawn a little generous, and adapters and pedestals come out as a generic 20 mm square. Print the extent with:
   ```
   python -c "import pyvista as pv; print(pv.read('component_library/mesh/KM200.ply').bounds[:4])"
   ```
   The four numbers are xmin, xmax, ymin and ymax, in that order:
   ```python
   "KM200": (-40.0, 9.0, -38.0, 38.0),
   ```
7. **Tell your board type how to hold it.** This only matters on boards whose parts don't stand on posts:
   - **Olego:** add the type to `OLEGO_PILLARS` in `optolayout/mounts3d.py` with the pillar it stands on. If the mount's base isn't under the optic, add the offset to `MOUNT_BASE_OFFSET`. See [docs/OLEGO_MATING.md](../docs/OLEGO_MATING.md).
   - **LightFlow:** add a `LightFlowElement` to `LIGHTFLOW_ELEMENTS` with the pedestal's footprint and screw holes. Without one, the part gets a plain pedestal the size of its footprint. See [docs/LIGHTFLOW_BOARD.md](../docs/LIGHTFLOW_BOARD.md).
   - **PyOpticL and posts on a grid or pre-drilled board:** nothing more is needed. The adapter or post is sized from the footprint and optic height.
8. **Check it.** Restart the app, place the part, and look at it in the Layout and 3D tabs. The mount should sit at beam height, face along the beam and match its 2D drawing.

Optionally, add an entry to `mounts.json` and to the table below, so that others know where the file came from. The app doesn't read `mounts.json`. It's a record of each model's source, size and optic height.

## Rebuild an existing model
The STEP files listed below aren't included. To rebuild a mesh, for example after a vendor update, save the file in `component_library/step/` with exactly the name in the table, and run `python tools/simplify_cad.py <name>`.

| 2D part types | Part | File name | Get it from | Optic above base |
|---|---|---|---|---|
| `mirror_1in` | Thorlabs KM100 | `KM100.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=KM100) | 25.40 mm |
| `mirror_half_in` | Thorlabs KM05 | `KM05.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=KM05) | 14.73 mm |
| `mirror_polaris_half` | Thorlabs POLARIS-K05S1 | `POLARIS-K05S1.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=POLARIS-K05S1) | 12.70 mm |
| `mirror_d` | Thorlabs DMM1 on a custom column | `DMM1_lab.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=DMM1) (DMM1 only) | 25.40 mm |
| `mirror_rd_1in`, `mirror_rd_half_in` | Radiant Dyes MDI-HS, 1" | `MDI-HS-2-3030.stp` | [radiant-dyes.com](https://www.radiant-dyes.com) (ask them if it isn't listed) | 26.50 mm |
| `mirror_newport_half` | Newport M05 | `Newport-M05.stp` | [newport.com](https://www.newport.com) | 12.66 mm |
| `hwp`, `qwp` | Thorlabs RSP1 | `RSP1.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=RSP1) | 27.73 mm |
| `hwp_half`, `qwp_half` | Thorlabs RSP05 | `RSP05.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=RSP05) | 13.98 mm |
| `hwp_crm`, `qwp_crm` | Thorlabs CRM1T | `CRM1T-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=CRM1T) | 22.40 mm |
| `fiber` | Thorlabs PAF2-A4A on HCA3 | `PAF2-A4A_on_HCA3.step` | [PAF2-A4A](https://www.thorlabs.com/thorproduct.cfm?partnumber=PAF2-A4A), HCA3 (combine the two) | 26.99 mm |
| `iris` | Thorlabs IDA12 | `IDA12.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=IDA12) | 13.3 mm |
| `lens_1in`, `fiber_cage` | Thorlabs CP33 | `CP33-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=CP33) | 20.32 mm |
| `lens_lmr1` | Thorlabs LMR1 | `LMR1-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=LMR1) | 22.10 mm |
| `shutter` | SRS SR475 | `3DSR475.stp` | [thinksrs.com](https://www.thinksrs.com) | 4.75 mm |
| power sensor | Thorlabs S121C | `S121C-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=S121C) | n/a |

Parts with no entry (cubes, AOMs, lasers, dumps, photodiodes) are always drawn as simple shapes. Olego pillars and LightFlow pedestals come with this repository as meshes in `mesh/Olego/` and `mesh/LightFlow/`, so they show in their real shape without any download. The STL files in `Olego_step/` and `lightflow small mount - new/` are included for printing or machining these parts.

## Line a model up
Every model has to be in the library frame:
- The origin is at the optic centre.
- +x is the optic normal / beam axis.
- +z is up, with the mount's base face below.
- Units are mm.

Files as downloaded usually aren't in this frame, and a model in the wrong frame shows up shifted or turned in the 3D view. `POSES` in `tools/simplify_cad.py` says how to move a file into the frame: the optic centre in the file's coordinates, the file direction that becomes +x, and the one that becomes +z.
- These parts already have a `POSES` entry, measured from their downloads: `MDI-HS-2-3030`, `Newport-M05`, `CP33-Step`, `CRM1T-Step`, `LMR1-Step`, `3DSR475`, `S121C-Step`. A newer vendor file may differ, so check them too.
- The rest need an entry of their own. To check one, compare its size with `bbox_mm` in `mounts.json`, which gives each model's extent in the library frame. [PyOpticL](https://github.com/UMassIonTrappers/PyOpticL) publishes transforms for many Thorlabs parts, and `cad_source` in `mounts.json` links to them.

## Sources
- The optic-centre heights come from PyOpticL `mount_position` where it exists; otherwise they come from the model's bounding box (`optic_center_height_source` says which).
- Vendor names and part numbers are their owners' trademarks. This project isn't affiliated with any of them.
