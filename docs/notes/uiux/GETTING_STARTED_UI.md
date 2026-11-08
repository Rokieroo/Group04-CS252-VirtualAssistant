# Getting Started and course actions

## UI implemented
- Active Library (route #sources, labelled Library) shows the prepared Getting Started catalog entry. It uses explicit origin=library and a stable built-in ID; titles are never used to infer origin.
- In UI preview mode, the tutorial is initially enrolled, appears on Roadmap, and opens four short feature lessons without syllabus verification.
- Preview enrollment is stored under pathly.preview.tutorial-enrollment.v1 in localStorage. A stored enrolled=false survives reload; re-enrollment changes the same record, without adding duplicates.
- Both Library and Roadmap read the same record. The preview is one shared browser profile, not per-account production persistence.
- Remove uses the existing accessible Modal, names the course and provides Cancel/Remove. Prepared lessons remain available for enrollment in Library.
- User-created roadmaps use a separate action panel and never feed the prepared catalog. Edit opens the existing syllabus editor with existing validation. Preview removal hides roadmap membership, retains the syllabus for editing, clears the displayed preview schedule and performs no backend deletion.
- Live removal/enrollment are disabled and explained because the current APIs cannot represent those operations.

## Verified
- Six tutorial component tests: initialization, cancellation, removal/remount, re-enrollment/no duplicate, personal-data isolation, undefined editing rules and live enrollment boundary.
- Personal-course flow test: generation, cancellation/removal, catalog isolation and retained syllabus editor.
- Actual Chrome at 1440x900 and 390x844: initial enrollment, lesson dialog/Escape, cancel, remove/reload, Library status, re-enroll/reload, navigation and no horizontal overflow.
- TypeScript/production build passes.

## Backend and product gaps
The active Course API currently provides owned course create/list plus materials; it exposes no prepared catalog, course origin, enrollment membership, course update or roadmap removal endpoint. CoreJourney also holds the active user-created roadmap in React state. The old demo enrollment implementation is isolated from the active app and must not be used as live persistence.

Production needs an explicit stable catalog ID/origin, authenticated user identity, membership read/enroll/remove operations, and a persisted once-per-user tutorial-initialization marker. Removal must retain this marker so reload does not re-enroll the tutorial. User-created course retention/deletion remains the existing backend's responsibility; no new deletion rule is implemented here. Account-backed initialization/reload behavior cannot be verified until those APIs exist.

Prepared-course editing needs a product decision: which fields may be personalized, whether prepared content is editable, and how edits behave on removal/re-enrollment. The Edit dialog identifies this gap instead of inventing permissions. User-created edits reuse the existing syllabus flow; there is currently no separate course metadata update API.
