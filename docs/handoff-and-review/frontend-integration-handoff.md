# Frontend integration foundation — handoff and PR review

Owner: Lê Phan Đức Mân (UI/UX, Developer).
Local branch: `codex/frontend-integration-foundation` (the repository permits the `codex/` prefix).

## GitHub comparison — 2026-10-28

This branch was fast-forwarded to `origin/main` at `94defe6`, which includes the
shell/login and upload/concept-editor work from PRs #26 and #27. The local foundation
was saved first in a stash named `Frontend foundation before merged UI integration
2026-10-28`; that backup is retained. The foundation remains uncommitted and unpublished.

The `App.tsx` conflict was resolved by integrating the extracted pages with mock login,
course context, Courses upload/editor, Companion and the desktop/mobile navigation.
Both navigation surfaces now share their labels and routes. Main's design tokens and
dark-mode styles are retained. Course upload/concept state stays mounted during page
navigation so edits are not discarded when checking another screen; reload still
clears this temporary state.

Browser tests now sign in (including after reload), use Courses/Review/Mastery, and
exercise the mock upload/editor alongside the learning checks. Issues #6 and #7 cover
the merged UI work; use a separately agreed issue for this learning-check foundation.

## What this change delivers

- Home, Schedule, Progress, Library and Reporter are separate page components. Navigation, modal, button and progress meter are shared components.
- Sample courses and initial sessions live in `ui/src/demo/fixtures.ts`; demo quiz keys and grading live in `ui/src/demo/checkService.ts`.
- The lesson dialog requests questions through `LearningCheckService`, then submits answer IDs. API mode uses the server result, including its pass decision; it does not calculate a score in the browser.
- Loading, empty, failure, retry and result states are implemented. Requests are cancelled on close. A submission retry retains its attempt ID and answers; the backend must implement idempotency.
- Question citations and response shapes are validated. API failures never silently fall back to sample questions.
- Component/service tests and desktop/mobile Chromium workflow tests run alongside the build in a new frontend CI job. Existing Python CI is unchanged.
- Visible tab names and guidance share `pageLabels` in `ui/src/navigation.ts`: Courses, Review, Ask, Mastery and Companion. Existing route IDs are retained for bookmarks. Shared buttons and learning-check states reuse the merged purple theme and design tokens, with 44 px minimum button/answer targets.

This is a frontend foundation. It preserves main's mock login and local PDF/concept demo, but does not add an API server, AI generation, real authentication, server uploads or database persistence. Concepts are fixed Week 1 examples rather than extracted from uploaded files. Courses, schedules, coaching and progress remain the local demo. API results do not update demo progress. Demo answers remain inspectable in the browser bundle; moving them into a demo module does not make them secure.

## Who to contact and request as PR reviewers

Names and roles below come from the root README and `docs/guidelines/GIT_WORKFLOW.md`. GitHub handles have not been verified; select their actual accounts in GitHub's reviewer picker.

| Reviewer | Role | Review request / question |
|---|---|---|
| **Lê Hồng Đăng** | QA/QC, Developer (`qa`, `devops`) | Review component/E2E tests, CI setup, failed-request behavior and screenshots. Run the verification commands below. Recommended primary reviewer from another role. |
| **Võ Gia Minh OR Trần Quyết Thắng** | AI-Integration, Security & Data (`ai`, `dbsec`) | Agree on the proposed check endpoints, stable session/question/option IDs, citations, server scoring and attempt replay. Confirm who will implement the backend adapter. |
| **Nguyễn Quốc Thịnh** | UI/UX, Security & Data (`uiux`, `dbsec`) | Review page extraction, keyboard/mobile behavior, feedback copy, public data fields and the demo/API distinction. |
| **Võ Thành Đạt** | Leader, Developer (`pm`, `devops`) | Confirm scope and follow-up ownership; review CI/deployment and the future authentication integration plan. Escalate cross-team decisions here. |

Suggested initial reviewer set: Đăng + one of Minh/Thắng + Thịnh. Add Đạt for the integration and delivery decision. This document does not assign work or notify anybody.

The repository requires at least one approval from another role or PM. Its guidance prefers PRs below approximately 400 changed lines. This foundation exceeds that because existing pages move into files and a tested API boundary is added. Review the mechanical extraction separately from the behavior changes; agree with Đạt whether to split these into separate PRs before publishing.

## Proposed contract — requires backend review

Types: `ui/src/api/types.ts`. Runtime validation: `ui/src/api/validation.ts`.
These endpoints are a proposed addition for the existing UI; they do not replace the concept/item/review endpoints in the app specification. AI/Data owners should agree on a mapping before implementing them.

### Load a check

`GET {baseUrl}/sessions/{sessionId}/learning-check`

```json
{
  "id": "check-1",
  "sessionId": "past",
  "title": "Past tenses",
  "kind": "subject",
  "questions": [{
    "id": "q1",
    "prompt": "Yesterday, she ___ to school.",
    "options": [{ "id": "go", "text": "go" }, { "id": "went", "text": "went" }],
    "citations": [{ "sourceId": "source-1", "fileName": "lesson.pdf", "page": 2 }]
  }]
}
```

The example is synthetic contract data. API questions require unique question IDs, at least two unique option IDs, and at least one citation with a positive, one-based page number. Citation labels are displayed as text; authenticated document navigation is a follow-up. An empty `questions` array displays an empty state. Do not include answer keys, private rubrics, or pre-submission explanations.

Current session IDs come from demo fixtures (`past`, `quiz`, `math-0`, etc.). A local backend test harness must map/seed those IDs. Real course/session API loading is a separate follow-up; this change does not invent a mapping to production records.

### Submit an attempt

`POST {baseUrl}/learning-checks/{checkId}/attempts`

```json
{
  "attemptId": "client-generated-uuid",
  "answers": [{ "questionId": "q1", "optionId": "went" }]
}
```

```json
{
  "checkId": "check-1",
  "sessionId": "past",
  "score": 100,
  "passed": true,
  "feedback": "Correct. Well done.",
  "explanations": [{ "questionId": "q1", "text": "Went is the past tense." }]
}
```

The backend owns question versions, score thresholds, user/course ownership, and persistence. Scope attempt IDs to the authenticated user and check; replay the same response for the same ID/payload and reject conflicting payloads. Retakes must not duplicate mastery credit. The UI preserves the ID on a timeout/retry and locks answer edits until that attempt resolves. A new practice attempt gets a new ID.

The client uses a 15-second timeout. It handles access denial (401/403), unavailable check (404), rate limiting (429), server/network failure, invalid JSON and invalid schemas. It displays safe client messages instead of raw server error bodies.

API mode currently uses `credentials: omit` and sends no authorization token. It is for local contract integration using synthetic data. Data/Security owners must approve and implement authentication, ownership validation, CORS/CSRF policy, server-side validation and safe persistence before real student data is used. All `VITE_*` values are public configuration; LLM keys belong on the server.

## Configuration and verification

Default: no config needed; run `ui/start.cmd` for the interactive demo.

To test a local service, copy `ui/check-config.example` to `ui/.env.local`, set `VITE_CHECK_MODE=api`, and point `VITE_API_BASE_URL` to your local API's `/api/v1` base. Restart Vite. `.env.local` is ignored by Git. The badge says "API checks · demo workspace". Invalid configuration shows an error and never selects demo mode automatically. Use HTTPS for remote API URLs.

From `ui/` in PowerShell:

```powershell
npx.cmd --yes pnpm@11.25.0 install --frozen-lockfile
npx.cmd --yes pnpm@11.25.0 exec playwright install chromium
npx.cmd --yes pnpm@11.25.0 check
```

From the repository root:

```powershell
.\.venv\Scripts\python.exe dev.py devops ci
git diff --check
git status --short
```

Browser tests start isolated Vite servers on ports 5178 (demo) and 5179 (API contract preview); leave these ports free. API tests intercept HTTP requests with synthetic responses. They validate the frontend contract, not a live backend or AI provider. Demo tests use desktop Chromium at 1440×900 and Pixel 7 emulation with a 390×844 viewport. Light/dark screenshots of learning checks and Review were inspected; this is not a physical-device, full accessibility or Safari/Firefox certification.

Passing demo tests save `knowledge-check.png` and `library.png` under `ui/test-results/`. Open `ui/playwright-report/index.html` for results. CI uploads these as `frontend-browser-results`. Add desktop/mobile screenshots to the PR per the team's UI review rule.

## Before opening the PR

Local verification completed on 2026-10-28 against merged main at `94defe6` plus this foundation:

| Check | Result |
|---|---|
| Frontend unit/component tests | 36 passed, including merged auth and concept tests |
| Browser workflows | 8 passed (desktop demo, mobile demo, mock login/upload/editor, API contract responses) |
| Production build | Passed |
| Python local CI | Passed; 27 tests, Ruff, secret scan and 20 benchmark cases validated |
| Dependency audit | No known vulnerabilities reported on 2026-10-25; not rerun on 2026-10-28 |
| Frozen-lockfile installation | Passed |
| Git whitespace check | Passed |

The browser checks cover login validation and re-login after reload, enrollment, search/empty results, lesson dialogs, calendar view preservation, quiz retakes, persisted demo progress and API failures/results. They also exercise rejected file types, mock PDF processing, concept rename/delete/undo/confirmation and preservation across navigation. The PDF fixture is synthetic input for the mock's checks, not validation of a real PDF parser. Login input names remain stable when errors appear. Desktop quiz and mobile course/concept screenshots were inspected. Decorative navigation icons are hidden from accessible names, and the mode label remains visible on mobile. Hosted GitHub CI and a live backend have not been tested by this local run.

- Link a real issue; the previously suggested `#22` was an example and was not verified.
- Suggested title: `[uiux-man] feat(ui): add learning-check integration foundation`.
- Describe the demo/API boundary, test results and remaining backend work.
- Include screenshots and select the reviewers above using their verified GitHub accounts.
- Confirm GitHub CI passes after pushing. Local success does not confirm hosted CI.

## Next work by role

| Owner | Next deliverable |
|---|---|
| UI/UX + Developer (Mân, with Thịnh) | Connect real course/session IDs after backend agreement; design document upload and authenticated source viewing. |
| AI (Minh/Thắng) | Implement question generation with source citations and approval rules behind the agreed API. |
| Data/Security (Minh/Thắng/Thịnh) | Implement authenticated ownership checks, server grading, persisted/idempotent attempts and progress. |
| QA (Đăng) | Extend the synthetic contract tests to a test backend; check accessibility and broader browser coverage. |
| PM/Developer (Đạt) | Resolve API ownership, issue split and deployment plan. |
