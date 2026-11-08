## Issue

Related to #7; follows the merged app-shell work in #6 and PRs #26/#27.
This PR does not close #7: staging verification is still outstanding.
The learning-check foundation is additional frontend work; please agree on a tracking issue for its backend integration.

## Đã làm (What changed)

After integrating main at `94defe6`, the learning-check foundation works with the merged mock login, navigation, PDF upload and concept editor.

- Split the large App into page components and shared navigation, dialogs, buttons and progress display.
- Added a learning-check service interface with separate demo and HTTP implementations. The HTTP client validates responses and citations and uses the server's grading result.
- Added loading, empty, error, retry and result states. Submission retries preserve the attempt ID and answers; the backend must implement idempotency.
- Preserved the merged shell, design tokens and course editor. Concept edits now survive navigation between pages, and login field labels remain stable when validation errors appear.
- Aligned headings, messages and navigation guidance with Courses / Review / Ask / Mastery / Companion. Shared buttons use the same token-based sizing as the upload/editor controls; learning-check answers, citations and status panels follow the purple theme in light and dark mode.
- Added frontend unit/component tests, desktop/mobile browser workflows and a frontend CI job.
- Updated Windows setup instructions and the integration/reviewer handoff.

## Scope and remaining work

The default UI still uses mock authentication, local PDF checks, fixed concept examples and pre-built quiz questions. Study progress is local to the browser. Upload/concept edits and the mock login last until reload.

API mode is a learning-check contract preview with synthetic tests. It sends no authentication credentials, does not generate questions, and does not update demo progress. Its proposed endpoints need agreement with the AI/Data owners before connection to the real backend. This PR does not complete #9, #10, #13, #14, #16 or #18.

## Cách kiểm tra (How to test)

From `ui/` in PowerShell:

```powershell
npx.cmd --yes pnpm@11.25.0 install --frozen-lockfile
npx.cmd --yes pnpm@11.25.0 exec playwright install chromium
npx.cmd --yes pnpm@11.25.0 check
.\start.cmd
```

Use mock credentials `student@example.test` / `demo-password`. Try a learning check, Courses upload/editor, navigation away and back, and reload/re-login.

From the repository root:

```powershell
.\.venv\Scripts\python.exe dev.py devops ci
git diff --check
```

Local results on 2026-10-28:

- 36 frontend unit/component tests passed.
- 8 browser tests passed, including desktop/mobile login, upload/editor and learning-check workflows.
- Production build and type check passed.
- 27 Python tests, Ruff, tracked-file secret scan and 20-case benchmark validation passed.
- No unresolved merge conflicts or whitespace errors.

Browser upload tests use synthetic input for the mock, not a real PDF parser. Hosted CI, live backend integration and staging still need verification. Demo workflows run at 1440×900 and 390×844; learning-check and Review screenshots were inspected in light and dark modes. This does not replace a full keyboard/accessibility audit or physical-device testing.

## Ảnh chụp màn hình

Attach desktop/mobile screenshots from `ui/test-results/`: `sign-in.png`, `course-concepts.png`, `knowledge-check.png`, `knowledge-check-dark.png`, `review.png`, `review-dark.png`, and `library.png`. The generated HTML report is `ui/playwright-report/index.html`; these artifacts are ignored by Git.

## Review requests

- **Đăng — QA/Developer:** review the regression tests and CI; independently verify UI workflows and staging with me.
- **Thịnh — UI/UX, Security & Data:** review accessibility, responsive behavior, and the future real-auth integration.
- **Minh — AI, Security & Data:** review the learning-check contract, citations and mapping to concept/item APIs; coordinate question generation and PDF ingest.
- **Thắng — AI, Security & Data:** review retrieval/source IDs and persistence implications where needed.
- **Đạt — PM/Developer:** confirm follow-up scope and ownership, including server grading/idempotency and whether this large refactor should be split for review.

## Checklist

- [x] Added tests and updated setup/integration documentation.
- [x] Local frontend and Python verification passed.
- [ ] Attach desktop/mobile screenshots.
- [x] Run demo workflows at 390 px and 1440 px; inspect learning-check and Review screenshots in both themes.
- [ ] Complete independent keyboard/accessibility review.
- [ ] Link the agreed learning-check follow-up issue.
- [ ] Obtain a reviewer approval and passing hosted CI before merge.
- [ ] Complete the staging demo/evidence for #7 before closing that issue.

## Responsibility handoff

My primary responsibility as UI/UX + Developer is the frontend: shell and reusable components, upload/concept interactions, learning-check states, accessibility/responsive behavior, frontend tests and documentation. I will connect the UI to agreed real APIs when available and work with QA on acceptance evidence.

The issue descriptions propose Thịnh for wireframes (#5) and real authentication (#14), Minh for concept extraction (#9), question generation (#10) and PDF ingest (#13), Thắng for retrieval (#11), and Đăng for independent integration QA (#16) and staging/deployment (#18). These are documented proposed owners, not new assignments made by this PR.
