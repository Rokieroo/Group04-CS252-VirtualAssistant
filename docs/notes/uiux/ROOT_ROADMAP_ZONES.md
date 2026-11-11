# Root roadmap: course sectors and count-dependent radial bands

## Local integration

Fetched main at `f82d571`, including merged PR #153 and the newer parser, graph motion and backend corrections. Merged it locally as `35176a9`, preserving course recovery commit `e77fc4c`. No remote updates were made.

## Creation and order review

Reviewed live generation/serialization (`routes_core.py`), topic/milestone linking (`app/roadmap/nodes.py`), persisted prerequisite edges (`roadmap_repository.py`), preview proposals (`api/core.ts`), offline parsing/generation (`demoParser.ts`, `mockCore.ts`), and the root view's `CoreJourney` integration.

The root view now consumes prerequisite edges and milestone `covers`, reuses the existing topological helper, and uses week then input order as tie-breakers. Cycles or duplicate IDs display an error instead of a misleading path. This is a display-order correction, not a change to saved syllabus or prerequisite data.

## Geometry

For a course containing N checkpoints, choose a shared safe radial extent across its usable angular corridor inside the parabola. With start R0 and end R1:

- step = (R1 - R0) / N
- low_n = R0 + (n - 1) * step + 2
- up_n = R0 + n * step - 2, for n = 1 ... N
- low_n + 15 + epsilon <= r_n <= up_n - 15 - epsilon

Thus up_n < low_(n+1). The entire node halo/focus outline fits within its radial band, not just its center. Angular clearance similarly accounts for the entire glyph. Each course retains its own approximately equal-area sector of the parabola. The common radius cap prevents angular movement from pulling a later node inward.

Bands recalculate separately for each course's current node count. The canvas expands when needed to preserve a minimum usable band width and clearance. Empty courses do not force expansion. Interpolated area quantiles avoid collapsed sectors when course counts exceed the angular sampling resolution.

Dragging converts screen coordinates through the SVG transformation matrix and projects the requested angle/radius into the same constraints used for rendering the node and path. Stored in-memory drag positions are reclamped after count changes. Cancellation clears pointer tracking. Click, drag-release and keyboard access still open descriptions.

Show geometry displays the actual parabola, course dividers and band boundaries. Large layouts scroll horizontally and vertically and initially center the home node vertically.

## Verification and scope

Geometry tests cover empty/single/unequal paths, dense multi-course layouts, full-circle containment at extreme drag coordinates, recalculation, prerequisite ordering, milestone coverage and cycle rejection. An isolated browser fixture checks actual SVG pointer dragging, changed checkpoint counts and description controls on desktop/mobile. It is not production course enrollment or persistence.

This affects the root roadmap. The week/force course knowledge graph retains its own layout/persistence. Root dragging remains in-memory UI state. Combining every account course into one root still requires the separate course/version-selection integration noted in COURSE_ROADMAP_RECOVERY.md.

## Local check results

- 213 Vitest tests passed across 37 files; final ordering/coverage integration also passed its focused 6-test rerun.
- TypeScript and production Vite build passed after the final changes.
- Full Playwright regression: 60 passed, 6 expected skips. Final root dragging/count-change checks passed on both desktop and mobile, including an assertion that the drag actually changed the radius.
- Local CI: 755 backend tests passed, plus Ruff, tracked-secret scanning and benchmark fixture validation.
- Dense geometry checks include 30-course full-glyph containment and finite sector calculations for 2,000 courses. The latter is a numeric robustness check, not a claim that such a large graph is comfortable to browse.
