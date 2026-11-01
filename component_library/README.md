# Component library

`mounts.json` lists the mounts used in 3D, with each one's product page, size and optic height. The 3D view reads the light meshes in `mesh/`, which come with this repository, so it shows the real mounts without any download. The full STEP files aren't included. A part with no mesh is drawn as a simple shape, and the status line in the 3D tab says which models are missing.

## Add or rebuild a model
1. Download the STEP file from the part's page below (on Thorlabs pages, look under the CAD tab).
2. Save it in `component_library/step/` with exactly the file name in the table. The name is how the app finds it.
3. Line it up (see below).
4. Run the converter, which needs `pip install cadquery-ocp pyvista`:
   ```
   python tools/simplify_cad.py KM100
   ```
   This writes a small mesh to `component_library/mesh/`, and that mesh is what the 3D view reads. Restart the app to see it.

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
