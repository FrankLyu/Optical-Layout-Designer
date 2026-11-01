# Optical Table Layout Designer & Power Logger

## 1. Project Goal

Develop a Python-based optical-table design and logging application for cold-atom experiments, conceptually similar to **KiCad for optical systems**.

The application should provide three integrated functions:

1. **2D Optical Layout Editor:** Design and modify the physical arrangement of optical components using a simple, clear, top-down interface.
2. **Optical Power Logger:** Record and track optical power measurements at specific locations along the optical paths, including their historical changes.
3. **3D CAD Generator:** Generate a detailed three-dimensional optomechanical assembly from the same 2D layout.

The 2D layout is the **primary workspace and single source of truth**. The 3D CAD model is generated on demand rather than edited independently.

### Visual References

- **2D:** Xingjian Lyu's 399 nm optical distribution drawing — clean, readable, top-down layout showing optical components and beam paths.
- **3D:** Infleqtion's Sqale optical-table CAD rendering — detailed, realistic mechanical models of optical mounts, posts, breadboards, and components.
- **Workflow:** KiCad — component toolbox, placement, rotation, project saving, and a consistent 2D-to-3D representation.
- **Existing software:** PyOpticL — reference for component libraries and Python-based CAD generation.

## 2. Core Requirements

### A. 2D Optical Layout Editor

The 2D interface should support:

- An optical-table workspace with physical dimensions and a 25.4 mm mounting-hole grid.
- A toolbox containing mirrors, lenses, AOMs, PBSs, waveplates, irises, fiber couplers, and other standard optical elements.
- Adding, deleting, moving, rotating, and labeling components.
- Snap-to-grid placement, with optional free positioning.
- Optical beam paths represented by colored lines.
- Manual definition and editing of beam connections between components.
- Saving and loading complete layouts.
- Zooming, panning, and exporting the drawing.

The layout should use **real physical coordinates**, not purely schematic positions.

Each component should have a persistent ID, position, orientation, type, and optional manufacturer model number.

**Initial limitation:** Automatic ray tracing, Gaussian beam propagation, and intelligent optical routing are not necessary. Beam paths can initially be drawn and edited manually.

### B. Optical Power Logger

The 2D editor should also act as a laboratory measurement record.

#### Measurement locations

- Each optical path between two adjacent components can contain a discrete measurement point.
- By default, the point is located at the midpoint of the path.
- Measurement points should be visible as small markers in the 2D layout.
- Clicking a marker opens its measurement history.
- Each point should have a unique persistent ID, independent of its displayed position.

Example:

```
Laser → [P1] → AOM → [P2] → PBS → [P3] → Fiber
```

#### Recording measurements

A user should be able to click a measurement point and enter:

| Field                  | Description                                   |
| ---------------------- | --------------------------------------------- |
| Optical power          | Measured power in mW, µW, or W                |
| Timestamp              | Automatically recorded, editable if needed    |
| Measurement point      | Automatically linked to the selected location |
| Notes                  | Optional experimental context                 |
| Wavelength             | Optional                                      |
| Measurement instrument | Optional                                      |

**Manual entry is sufficient for the initial version.** Automatic acquisition from a power meter can be added later.

#### Historical tracking

Each measurement point should maintain its complete history.

For example:

**P2 — After AOM**

| Date  | Power (mW) | Notes             |
| ----- | ---------- | ----------------- |
| Oct 1 | 25.4       | Initial alignment |
| Oct 3 | 23.1       | Before cleaning   |
| Oct 3 | 26.8       | After cleaning    |
| Oct 9 | 25.9       | Routine check     |

The interface should provide:

- The latest measured power displayed near the marker.
- A measurement-history table.
- A time-series graph of optical power.
- Absolute and percentage changes between measurements.
- Optional color highlighting for significant power changes.
- Optional notes explaining changes.

Measurements should be **append-only by default**, preserving the original history.

#### Preserving measurements when the layout changes

This is an important requirement.

- Moving or rotating an optical component must not delete its measurement history.
- Measurement records should be associated with stable measurement-point IDs, not just X/Y coordinates.
- If an optical path is removed or split into new segments, its historical measurements must remain accessible.
- Old measurement locations can be archived without losing their records.

This avoids losing laboratory data as the optical setup evolves.

#### Storage

A local SQLite database is recommended for measurement records.

The layout itself can be stored in JSON or YAML.

Both should be portable and easy to back up. No online database or server is required initially.

### C. 3D CAD Generator

Generate a 3D optomechanical assembly from the 2D layout.

Each component in the toolbox should have:

- A simplified 2D symbol.
- An optional detailed 3D CAD model, preferably STEP.
- Mechanical mounting information.
- Position and orientation information.
- A defined optical-axis height.

The 3D assembly should include:

- Optical breadboards or tables.
- Mirrors, lenses, PBSs, AOMs, and other optical components.
- Mounts, posts, and bases.
- Correct physical spacing and orientation.

#### Synchronization

The 3D model must be derived directly from the 2D layout.

**Workflow:**

1. Modify components in 2D.
2. Save the layout.
3. Click **Generate / Update 3D**.
4. The CAD engine rebuilds the assembly using the latest coordinates.
5. Inspect the 3D model and export when necessary.

Independent 3D editing or bidirectional synchronization is not required.

FreeCAD and PyOpticL are preferred starting points.

## 3. Suggested Development Milestones

### Milestone 1 — Functional 2D Layout Editor

**Priority: Highest**

Build a simple, reliable editor for arranging optical elements.

Deliverables:

- Optical-table grid and physical coordinates.
- Basic optical component toolbox.
- Component placement, dragging, and rotation.
- Manually defined optical paths.
- Component labels and IDs.
- Save/load layout files.
- Undo/redo for layout changes.
- Export as an image or SVG.

**Success criterion:** A complete 399 nm or 626 nm optical distribution board can be recreated and subsequently edited entirely in the 2D interface.

### Milestone 1.5 — Optical Power Logger

**Priority: High — immediately after Milestone 1**

Integrate the measurement logger into the existing 2D workspace.

Deliverables:

- Discrete measurement points along optical paths.
- Clickable measurement markers.
- Manual optical power entry.
- Automatic timestamps.
- SQLite measurement database.
- Measurement history and time-series plots.
- Display latest measured power directly on the layout.
- Preserve records when components move.
- Archive measurement points when paths are removed.

**Success criterion:** The software can be used during daily laboratory operation to record and compare optical powers at different locations, without maintaining a separate spreadsheet.

This milestone should be completed **before starting substantial 3D CAD development**, since the logger provides immediate practical value.

### Milestone 2 — 3D CAD Generation

**Priority: Medium**

Develop a component-model library and 3D assembly generator.

Deliverables:

- Basic 3D component and mount library.
- STEP model import.
- Optical-table and breadboard generation.
- Correct positioning and rotation of components.
- Matching optical-axis heights.
- 3D preview.
- STEP export for the complete assembly.
- Regeneration after 2D layout changes.

**Success criterion:** A saved 2D layout can be converted into a mechanically consistent 3D optical assembly resembling the Infleqtion-style CAD rendering.

Photorealistic rendering is desirable but not essential initially.

### Milestone 3 — Basic Optical Ray Tracing

**Priority: Low — future development**

Implement only the optical behavior that materially improves layout editing.

The primary feature would be:

- Correct geometric reflection from mirrors.

Possible later extensions:

- Beam direction updating when mirrors are rotated.
- Transmission and reflection through PBSs.
- Basic beam-branch tracking.

Not planned initially:

- Gaussian beam propagation.
- Wavefront or aberration simulation.
- Automatic optical alignment.
- Automatic path optimization.
- Full physical optics simulation.

**Success criterion:** Changing a mirror's angle can automatically update the reflected beam direction in the 2D layout.

This milestone should not delay the implementation of the logger or the 3D CAD generator.

## 4. Suggested Technical Architecture

| Subsystem               | Recommended technology         |
| ----------------------- | ------------------------------ |
| Main language           | Python                         |
| Desktop UI              | PySide6 / Qt                   |
| 2D graphics             | QGraphicsScene / QGraphicsView |
| Layout storage          | JSON or YAML                   |
| Measurement history     | SQLite                         |
| History plots           | PyQtGraph                      |
| 3D CAD generation       | FreeCAD / PyOpticL             |
| Mechanical model format | STEP                           |
| 3D visualization        | FreeCAD viewer initially       |

### Core Architectural Principles

1. **One shared layout data model:** The 2D display, logger, and 3D generator reference the same optical components and paths.
2. **Persistent IDs:** Components, beam segments, and measurement points must retain stable identities across edits.
3. **Separate geometry and measurements:** Changing the layout must not erase or overwrite historical measurements.
4. **Modular component library:** New optical components can be added without modifying the entire application.
5. **2D-first workflow:** Routine editing and measurement logging must work even if FreeCAD is not installed or running.
6. **On-demand CAD:** 3D assemblies are generated only when requested.
7. **Local-first:** Projects and measurement history remain accessible without internet connectivity.

## 5. Recommended Initial Scope

Start with a single optical breadboard containing:

- One laser or fiber input.
- Three to five steering mirrors.
- One AOM.
- One PBS.
- One waveplate.
- One fiber output.
- Four to six optical power measurement points.

Use this system to validate the 2D editor, measurement logger, persistence, and subsequent 3D conversion before expanding the component library.

### Final Priority Order

**1. 2D Layout → 1.5. Power Logger → 2. 3D CAD → 3. Mirror Reflection**

The primary objective is a **practical optical-table layout and laboratory documentation tool**, rather than a sophisticated optical simulation package.

The most valuable end product is an optical-table drawing that remains useful throughout an experiment's lifetime: it documents where components are placed, how beams are routed, what optical powers have been measured, and how those measurements change over time.