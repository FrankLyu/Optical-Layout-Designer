## 3D render (Milestone 2 prototype)
```
pip install cadquery-ocp mitsuba
python tools/render3d.py examples/demo_3d_simple.json examples/render/demo.png --theme dark
```
- `optolayout/cad3d.py` turns the 2D layout into a 3D assembly. Each part gets its Thorlabs STEP model from `component_library/step` at beam height (default 2" = 50.8 mm, `--beam-height`) on a Ø1" Thorlabs pedestal post with a clamping fork. The post length is cut to whatever puts each optic at the beam height. The breadboard and beams are added too.
- `tools/render3d.py` renders a studio image with Mitsuba. `--theme dark` gives the dark keynote look and `--theme light` a white product shot. Use `--spp` for quality and `--size WxH` for resolution. It also writes a `.step` of the assembly next to the PNG, which opens in FreeCAD.
- 3D models exist for 1" and ½" mirrors, waveplates, the fiber launcher and the iris. Other types are skipped for now. Radiant Dyes mounts use the KM100 model until their CAD is available.
- `examples/make_demo_3d.py` makes the simplest test layout: an iris, two mirrors and a fiber coupler.

## 3D tab (live view in the editor)
- The **3D** tab (Ctrl+3) shows the board in real time: drag to rotate, wheel to zoom, Shift+drag to pan, F to fit. It follows the Layout tab, where parts are moved. Set the beam height at the top of the tab; posts are cut to match.
- It needs `pip install pyvista pyvistaqt`. Without them, the tab says how to install them and the rest of the app works as before.
- Vendor mounts use light meshes in `component_library/mesh/` (about 8000 triangles each; Olego pillars at full detail). After adding a STEP file, run `python tools/simplify_cad.py` to make its mesh (needs cadquery-ocp). Parts without CAD (Radiant Dyes mounts, cubes, cage plates, shutter, AOM, laser...) are drawn from simple shapes in `optolayout/view3d.py`.
- File → Export PNG on the 3D tab saves the current view.
