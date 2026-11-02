# Pathly interactive UI

React + TypeScript frontend for the CS252 study assistant. The Python CLI stays independent. This implements the supplied Pathly Figma concept as five pages and reusable interaction states.

## Platform

Pathly is a responsive browser application built with React, TypeScript, and Vite. Development is supported on Windows, macOS, and Linux. The finished static build runs in current versions of Chrome, Edge, Firefox, and Safari, including mobile browsers. It is not currently a native Windows, Android, or iOS application.

The UI defaults to a local demo: login and PDF/concept processing are mocked, with no real account, cloud synchronization or AI generation. Study progress stays in browser localStorage. Login and uploaded-file/concept state stay in memory; reloading signs you out and clears that temporary state. The repository's Python LLM/database modules are not connected to these screens yet.

## Requirements

- Node.js 24.22.1 LTS or a newer Node 24 LTS security patch
- npm, which is included with the standard Node.js installer
- A modern web browser
- Internet access for the initial download and dependency installation
- Git only when cloning; it is not required when using a ZIP download

Python, Docker, API keys, and a database are not required for the UI.

## Download

### Option 1: Git

```bash
git clone https://github.com/MorganConsort/Group04-CS252-VirtualAssistant.git
cd Group04-CS252-VirtualAssistant/ui
```

### Option 2: ZIP

Open the GitHub repository, choose **Code → Download ZIP**, extract it, and open a terminal in the extracted `ui` folder.

## Install and run

From the repo root you can also use the project CLI: `python dev.py ui install`, then `python dev.py ui dev` (and `ui build`, `ui test`).

The app opens on a mock login/register screen (`src/api/mock.ts`): any valid email, a password of at least 8 characters, and (to register) a birth year from 1900 to this year will sign in. The token lives in memory only, so reloading the page signs you out.

For example, use `student@example.test` and `demo-password`. Use sample credentials, not a real password.

From the `ui` folder:

```bash
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://127.0.0.1:5173`.

Windows users who already installed the dependencies can alternatively run the Command Prompt launcher. It also works when PowerShell script execution is disabled:

```bat
start.cmd
```

The repository also includes `start.ps1`, but Windows may block unsigned PowerShell scripts depending on the computer's execution policy. The `.cmd` launcher avoids requiring an execution-policy change. macOS and Linux users should use `npm run dev`.

## Build for deployment

```bash
npm run build
npm run preview
```

`npm run build` type-checks the project and writes deployable static files to `dist/`. The `dist/` folder can be served by a static web host. Run `npm test` to check state transitions. Maintainers can use pnpm 11.25.0 with the included lockfile instead of npm.

### Hosted demo (GitHub Pages)

Every push to `main` that touches `ui/` runs `.github/workflows/pages.yml`, which publishes the offline demo (no backend, no AI calls) to `https://<owner>.github.io/<repo>/`. `npm run build:pages` builds the same thing with relative asset paths, so `dist/` works from any sub-folder of any static host; the app's `#hash` routes need no server rewrites. Build it without `VITE_BACKEND_MODE=api` (remove it from `.env.local`, or run `VITE_BACKEND_MODE=demo npm run build:pages`) so the page never calls a server.

### Real concept extraction

Put `VITE_BACKEND_MODE=api` in `ui/.env.local`, start the backend (`python -m uvicorn assistant.backend.main:app --app-dir src --port 8000` from the repo root), then `npm run dev`. Sign-in, PDF upload and concept extraction then use the backend at `VITE_API_URL`; extraction can take a minute or two per file. `e2e/concepts.spec.ts` covers this mode against a mocked backend.

## Troubleshooting

- `node` or `npm` is not recognized: install Node.js 24 LTS, close the terminal, and open a new one.
- PowerShell reports that scripts are disabled: run `.\start.cmd` instead of `.\start.ps1`.
- PowerShell blocks `npm.ps1`: use `npm.cmd` or `npx.cmd` in place of `npm` or `npx`.
- `pnpm.cmd` is not recognized: use `npx.cmd --yes pnpm@11.25.0` in its place, from the `ui` folder. This runs the project's pinned pnpm version without a global installation; the first run needs internet access.
- Dependencies are missing: run `npm install` again in the `ui` folder.
- Port 5173 is busy: run `npm run dev -- --port 5174` and open the printed URL.
- To reset the demo: remove the `pathly.demo.v1` entry from the site's browser local storage.

## Try the workflows

- Home: start a lesson, mark it studied, and pass its knowledge check. Reading does not award progress; passing the same session twice awards credit only once.
- Review (Schedule): navigate weeks/months, return to Today, and select any session.
- Courses: try the local PDF upload and concept editor, then search/filter the sample library below it. Concept edits survive navigation between pages until reload. The proposed concepts are fixed Week 1 examples, not extracted from your uploaded PDF.
- Ask (AI Reporter): try `learn Math 7`, `learn Physics`, `learn History 9`, `learn Biology 9`, `adjust workload`, or `weekly report`.
- Mastery opens course progress; Companion is a placeholder. Select the Pathly logo in the sidebar to return Home.
- Confirm the prerequisite, review the proposed plan, and approve enrollment. New sessions appear in the calendar. History starts at level 7; later levels remain conditional.
- Save a module to the future plan without adding sessions. Find it under Courses → Saved for later.
- Settings: change the display name and available weekly hours. Use Adjust workload to explicitly approve schedule changes.

## Prototype boundaries

No API keys, backend, database, or real LLM are needed. AI replies are deterministic examples, prerequisite confirmation is self-reported, schedule topics are sample data, and workload uses an illustrative 3 hours per active course estimate. Weekly budget adjustment resizes existing planned sessions (10–60 minutes), not a scheduling optimizer. English has four sample grammar questions; other modules use a clearly labeled workflow check. Mastery lists the scheduled demo sessions and updates each status after a passing check. The initial English goal begins with six example lessons already completed, plus seven scheduled sessions (6/13 verified).

State is stored under `pathly.demo.v1` in browser localStorage, not an account. Lesson scratch notes last only while the dialog is open. Removing that storage key resets the demo. Saved demo schedules are rebased when the date changes so the relative calendar remains usable.

## Code map

- `src/App.tsx`: workspace state, navigation and scripted coaching orchestration.
- `src/pages/`: Home, Schedule, Progress, Library, Reporter and the merged Courses upload/editor view.
- `src/auth.ts`, `src/components/AuthScreen.tsx`, `src/api/mock.ts`: mock login/register and course context.
- `src/concepts.ts`, `src/api/courses.ts`: concept graph operations and mock PDF/concept processing.
- `src/components/`: shared navigation, buttons, accessible modal and progress meter.
- `src/domain.ts`, `src/model.ts`: workspace types, demo persistence and state transitions.
- `src/demo/`: sample courses/sessions and the local quiz adapter (not secure grading).
- `src/api/`: proposed learning-check types, response validation, configuration and HTTP adapter.
- `src/features/learning-check/`: lesson dialog and asynchronous check UI.
- `src/styles.css`: shared Figma colors, typography, cards, sidebar, responsive layouts.
- `src/model.test.ts`: progress, future-plan, enrollment, and workload invariants.
- `src/**/*.test.*`, `e2e/`: service/component and desktop/mobile browser regression tests.

## Learning-check integration and frontend checks

Default mode still runs entirely as a demo. Questions are pre-built; no AI provider is connected.
For local backend integration only, copy `check-config.example` to `.env.local`, change
`VITE_CHECK_MODE` to `api`, set `VITE_API_BASE_URL`, and restart Vite. Only learning checks use
that API. Courses, scheduling and coaching stay in the demo; API results do not change its
local progress. Failed requests show an error and retry action, never fallback questions.
No authorization token or cookies are sent yet. Do not use this preview with real student data.

Maintainer verification (PowerShell; the `.cmd` suffix avoids script-policy errors):

```powershell
npx.cmd --yes pnpm@11.25.0 install --frozen-lockfile
npx.cmd --yes pnpm@11.25.0 exec playwright install chromium
npx.cmd --yes pnpm@11.25.0 check
```

`pnpm check` runs unit/component tests, the production build and browser tests. Browser
tests use dedicated ports 5178/5179 and synthetic API responses. CI runs the same frontend
checks and uploads browser screenshots/reports. The Python `devops ci` command remains a
separate check and does not run the frontend suite.

See [frontend integration handoff](../docs/frontend-integration-handoff.md) for API examples,
reviewer names and roles, limitations, and the PR preparation checklist.

## Design source

https://www.figma.com/design/VG4biz9VR4o9dDg24Gl0BI

High-fidelity context was retrieved for Home, weekly Schedule, selected lesson, Library, course Progress, Reporter, Physics request, balanced proposal, History approval, overload warning, and deferred confirmation. Figma's Starter API limit prevented retrieval of some alternate states, including the monthly calendar; those interactions reuse the retrieved components. No screenshot is used as an implementation asset. The Code Connect `Book` component was not present in this Python starter, so the shared navigation uses the Library glyph supplied by the Home design. Inter is bundled locally through `@fontsource/inter`.

## Scheduling Workspace

Open `/#workspace` for the optional account-backed task planner. Start `assistant.backend.main:app` on port 8000 first. Workspace has its own account/session flow, separate from the course demo login. `VITE_API_URL` selects this scheduling backend; the course check API keeps its existing configuration. See [the scheduling handoff](../docs/minh-handoff.md).
