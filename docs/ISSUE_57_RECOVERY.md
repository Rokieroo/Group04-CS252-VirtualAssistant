# Recovery of local #57 work onto main

Base: cd34e0e. Branch: uiux-man/57-roadmap-integration.
The complete original backup remains in stash@{0}, including obsolete backend changes. It was not popped.

Recovered: tutorial component and tests, personal-course actions, timeline/status presentation, schedule feedback, keyboard improvements, screenshots, planner weekly budgets and regression tests.
Preserved from main: separated mock service, syllabus goals flow, NodeMaterials, live course/material screens, Workspace and migrations 0008 through 0012.

Graph saving now diffs against GET /roadmaps/{id}/edges and uses the existing POST/DELETE edge endpoints with their server-side cycle validation. The authenticated GET endpoint is added here. There is no new graph table, edges_json column or migration.

Verification: frontend unit suite, production build, desktop/mobile graph edit/approval/schedule tests; backend schema/OpenAPI and weekly-budget/prerequisite tests. A real CSC10014 text fixture is parsed, passes blocking checks, is saved and generates topic/milestone nodes with no supplied dummy nodes. This is separate from the prepared Getting Started tutorial, whose enrollment remains preview-only.

Environment: main pins Pillow~=10.3, but this computer only has Python 3.15. Installing the declared dependency fails to build. Local verification uses Pillow 13's compatible wheel. requirements.txt remains unchanged; use a compatible Python for exact pinned-environment verification.

Known backend/product boundaries: define/expose authoritative node statuses (the restored UI currently falls back to available), verify the completeness of the live syllabus-to-week timeline (the generator may derive topics from CLOs), and review approval draft/active persistence semantics. Current setup state still does not restore after browser reload. Edge saves are incremental API calls; a failure may leave part of the edit applied and retry reconciles against the server.

The PR includes the requested Getting Started preview alongside the root-graph UI. Per-account enrollment and prepared-course editing rules remain backend/product gaps; see GETTING_STARTED_UI.md.
