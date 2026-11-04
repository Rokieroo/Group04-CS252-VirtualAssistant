# S3–S5 redesign and refactor

The default entry is now CoreApp. Previously a normal `pnpm dev` opened the old demo; it is still available with `VITE_BACKEND_MODE=legacy-demo`.

Run `ui/start-preview.ps1` to serve this checkout at http://127.0.0.1:5173. Stop an existing Vite process first if that port is occupied. The strict port option prevents silently opening a different port.

## Active implementation

- `ui/src/App.tsx`: new interface by default, backend authentication in `VITE_BACKEND_MODE=api`, preserved Old app only in `VITE_BACKEND_MODE=legacy-demo`.
- `ui/src/pages/CoreJourney.tsx`: setup state and service orchestration. Upload, review and roadmap approval remain in Courses. Completion offers return or view roadmap.
- `ui/src/CoreApp.tsx`: in API mode, Courses also mounts the slide concept editor (`CoursesPage`) and Schedule/Workspace render the real `Workspace`; the sample preview has no backend for them.
- `ui/src/api/core.ts` holds the shared types and the live service; `ui/src/api/mockCore.ts` holds the labelled sample-data service; `ui/src/api/syllabus.ts` owns input checks, validation and the syllabus API adapter.
- `ui/src/pages/course-setup/SyllabusUpload.tsx`: file selection, drop area, optional pasted text, explicit Continue action.
- `ui/src/pages/course-setup/SyllabusReview.tsx`: four editable sections, source evidence, validation and confirmation.
- `ui/src/pages/course-setup/RoadmapTimeline.tsx`: weekly cards, selected-week details, plan settings, learning goals and milestones.
- `ui/src/pages/course-setup/study-companion.css`: scoped Figma styling. Landscape navigation is left; portrait/square navigation is top. The required core navigation remains Courses, Roadmap, Schedule, Library and Settings; extra Figma Home/Progress destinations have not been invented.
- Existing native Modal handles source citations and scheduling, including Escape and focus containment.
- `ui/src/navigation.ts` defines menu order. Reorder `nav`, update `pageLabels` for labels, and add the destination to CoreApp's headings and the page renderer to introduce a tab.

## Old files retained

Files in `ui/src/demo` (and `RoadmapPage`, which only the demo uses) carry an `Old` comment: they serve the legacy demo, not the redesigned journey. Git history keeps the pre-refactor CoreJourney.

The original gradient-picker work is preserved in the pushed `old/gradient-picker` branch. The five selected gradient definitions for this redesign are in `ui/src/features/appearance/gradients.ts`.

## Verification and limits

Issue #56 now connects PDF/DOCX/text upload, four-section editing, source citations, validation and confirmation to the backend. All reviewed fields are persisted in the existing syllabus raw_text JSON snapshot, with outcomes and assessments also stored in their normalized fields. See [issue #56 verification](ISSUE_56.md) and [run instructions](../ui/README.md#real-syllabus-upload-and-review-56).

Default mode remains a labelled sample preview. Setup state does not automatically restore after reload. Roadmap prerequisite edits remain session-only and the live backend regenerates its roadmap on approval; these #57 limitations are not resolved by #56. S8 remains the existing empty Library page.
