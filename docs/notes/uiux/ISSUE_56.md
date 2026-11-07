# Issue #56: syllabus upload and review

## Implemented

- S3 accepts PDF/DOCX (up to 20 MB), drag/drop and pasted text (up to 120,000 characters), with duplicate-submit protection and retry.
- Vietnamese messages cover HTTP 400/413/415/422. Mock mode remains available without a backend.
- S4 provides editable outcomes, weeks, assessments and textbooks, including add/delete, metadata, readings, assessment dates and required-textbook flags.
- Source-page buttons open extracted page text. PDF line breaks and pasted-text page mappings are preserved by the backend.
- Blocking warnings disable confirmation and recalculate after edits. Unknown blocking API warnings remain blocking; source-grounding warnings require explicit manual review acknowledgement.
- Confirmation persists the complete reviewed snapshot in the existing raw_text JSON field, plus normalized outcomes/assessments, using the authenticated user's course.
- Keyboard navigation includes arrow-key tabs, visible focus, dialog Escape/focus restoration, stage/error focus and save announcements.
- Navigation stays left in landscape and top in portrait. In API mode Courses also keeps the slide concept editor below the syllabus setup, and Schedule/Workspace stay on the real Workspace.

## Verification

- Frontend: 100 unit tests passed; TypeScript and production build passed.
- Changed Python files: Ruff passed.
- Backend: 513 tests passed (one third-party deprecation warning).
- Browser suite: 24 tests passed, including S3/S4 desktop/mobile, keyboard-only confirmation, errors and retry, and processing states.
- Isolated real backend: CSC10014 PDF, DOCX and text at 1440×900 and 390×844; source citations, corrected fields and persisted confirmation verified.
- Screenshots: screenshots/56/live-review-1440.png and live-review-390.png.

From repository root, run the live smoke test with Node and Chrome installed, frontend dependencies installed, and backend requirements installed in .venv:

```powershell
node ui/scripts/check-syllabus-live.mjs
```

It starts its own in-memory backend on 8012 and frontend on 5182, uses synthetic account data and shuts down its own processes. SYLLABUS_TEST_PYTHON can override the Python interpreter; PLAYWRIGHT_CHANNEL can override Chrome.

## API decisions and remaining boundaries

The current parse endpoint is synchronous and exposes no job/poll endpoint. The UI therefore uses indeterminate progress; polling awaits an actual asynchronous backend contract. Citations display extracted text, not a rendered original PDF. Saved data persists, but reopening the setup draft after a page reload is not implemented. Roadmap approval/edit persistence belongs to #57 and remains outside this change. No GitHub issue closure or PR publication is performed by this implementation.
