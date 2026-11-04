# S3–S5 redesign and refactor

The default entry is now CoreApp. Previously a normal `pnpm dev` opened the Old demo unless `VITE_BACKEND_MODE=core-mock` was set. This D: checkout now has the redesign on `codex/core-ui`, based on the latest `main`. The previous gradient-picker state remains on `old/gradient-picker`.

Run `ui/start-preview.ps1` to serve this checkout at http://127.0.0.1:5173. Stop an existing Vite process first if that port is occupied. The strict port option prevents silently opening a different port.

## Active implementation

- `ui/src/App.tsx`: new interface by default, backend authentication in `VITE_BACKEND_MODE=api`, preserved Old app only in `VITE_BACKEND_MODE=legacy-demo`.
- `ui/src/pages/CoreJourney.tsx`: setup state and service orchestration. Upload, review and roadmap approval remain in Courses. Completion offers return or view roadmap.
- `ui/src/pages/course-setup/SyllabusUpload.tsx`: file selection, drop area, optional pasted text, explicit Continue action.
- `ui/src/pages/course-setup/SyllabusReview.tsx`: four editable sections, source evidence, validation and confirmation.
- `ui/src/pages/course-setup/RoadmapTimeline.tsx`: weekly cards, selected-week details, plan settings, learning goals and milestones.
- `ui/src/pages/course-setup/study-companion.css`: scoped Figma styling. Landscape navigation is left; portrait/square navigation is top. The required core navigation remains Courses, Roadmap, Schedule, Library and Settings; extra Figma Home/Progress destinations have not been invented.
- Existing native Modal handles source citations and scheduling, including Escape and focus containment.
- `ui/src/navigation.ts` defines menu order. Reorder `nav`, update `pageLabels` for labels, and add the destination to CoreApp's headings and the page renderer to introduce a tab.

## Old files retained

Every source/test file in `ui/src/demo` and the replaced CoursesPage, RoadmapPage and SourcesPage has an `Old` comment. The pre-refactor CoreJourney is retained as `course-setup/CoreJourney.old.tsx.txt` with an `Old` comment; the text extension keeps archived relative imports out of compilation. Shared modules still used by the active interface are not labelled obsolete.

The original gradient-picker work is preserved in the pushed `old/gradient-picker` branch. The five selected gradient definitions for this redesign are in `ui/src/features/appearance/gradients.ts`.

## Verification and limits

84 unit tests pass, production build passes, and `node ui/scripts/check-course-setup.mjs` (run from ui instead as `node scripts/check-course-setup.mjs`) checks the actual default server at 1440×900 and 390×844. Chrome must be installed. It checks review sections, source dialog dismissal, explicit approval, navigation and horizontal overflow. Screenshots are in `docs/screenshots/56-57/refactor-*`.

Default mode uses a labelled sample syllabus; it does not parse uploaded files. Live API currently accepts pasted text and persists outcomes/assessments; weeks, textbooks and prerequisite edits remain session-only. The backend regenerates its own roadmap on approval. Setup state does not survive reload. S8 remains an empty future library destination. This refactor does not implement those missing backend capabilities.
