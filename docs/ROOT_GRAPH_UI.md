# Root graph roadmap

Figma reference: Yfa1Gx8dJNUDqJDjKQrqxW / 33:658.

RootRoadmap receives a dynamic course list: each course produces exactly one path. No screenshot course names or completion counts are hardcoded. CoreJourney supplies the enrolled preview tutorial and the current approved personal roadmap. Account-wide multi-course loading and restoration remain limitations of the existing course state/API; this UI does not fabricate those records.

Geometry: y² <= H²*x/L, clipped at x=L. Numerically integrate radial area (one half radius squared) to choose equal-area angular quantiles. n courses yield n-1 internal separator rays. Checkpoints sit near circular radial arcs with deterministic variation within the corresponding lane. Geometry is hidden unless Show geometry is enabled. Node dragging is a transient visual adjustment inside its lane; it updates the rendered course path and opens the description on release. No prerequisite or backend layout changes are made.

Click, Enter or Space opens the existing accessible Modal. Course cards select/highlight a path. Mobile keeps usable node targets in a horizontally scrollable graph region while the legend stacks below. Empty and single-course states use the same component.

The Figma graph vectors represent example course data. Production paths/nodes are generated from actual course data rather than embedded as fixed images. Existing shell/nav/components remain in use.

Verification: geometry tests for 1/2/5/12 courses (equal area within 2%, divider count, lane/parabola bounds); dynamic five-course rendering and keyboard details; Chrome 1440x1000 and 390x844 click/keyboard, desktop drag, geometry toggle and horizontal overflow checks. Full frontend suite: 114 tests passed. Build passes. Drag offsets are not persisted. Unknown progress is not invented.
