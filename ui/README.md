# Pathly interactive UI

React + TypeScript frontend for the CS252 study assistant. The Python CLI stays independent. This implements the supplied Pathly Figma concept as five pages and reusable interaction states.

## Platform

Pathly is a responsive browser application built with React, TypeScript, and Vite. Development is supported on Windows, macOS, and Linux. The finished static build runs in current versions of Chrome, Edge, Firefox, and Safari, including mobile browsers. It is not currently a native Windows, Android, or iOS application.

The UI defaults to the redesigned Courses → syllabus review → roadmap approval preview. It uses sample syllabus data and does not parse uploaded PDF/DOCX files. The previous Pathly demo is preserved under `VITE_BACKEND_MODE=legacy-demo`; use `VITE_BACKEND_MODE=api` for the connected backend.

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

From the repo root, use the project CLI:

```bash
python dev.py ui install
python dev.py ui dev
```

Open `http://127.0.0.1:5173`. This now opens the redesigned Courses screen. To run the project's checks, use `python dev.py ui test` and `python dev.py ui build` from the repo root.

The default preview opens directly on Courses with sample data. In API mode, sign in to use the connected service.

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

### Real syllabus upload and review (#56)

For real PDF/DOCX parsing and saving, run two terminals from the repository root.
Install backend dependencies first using your project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn assistant.backend.main:app --app-dir src --port 8000
```

In the second terminal:

```powershell
$env:VITE_BACKEND_MODE="api"
.\.venv\Scripts\python.exe dev.py ui dev
```

Open the URL Vite prints, register/sign in, and open Courses. Upload a PDF/DOCX or paste text, review the four sections, correct blocking warnings, then confirm. The backend defaults to http://127.0.0.1:8000 (override with VITE_API_URL). Restart Vite after changing mode. Default preview uses sample data; it does not parse your file.

The parser returns synchronously, so processing shows an indeterminate indicator rather than invented percentages. Source citations open extracted text for that page. Confirmation saves all reviewed sections; automatic restoration of the setup screen after reload is not implemented.

See [issue #56 verification](../docs/notes/uiux/ISSUE_56.md) for acceptance checks and the isolated real-backend smoke test. The concept-extraction browser test (`e2e/concepts.spec.ts`) still runs in the `backend-ui` project.

## Knowledge Graph Rendering & Architecture (#108)

For interactive course knowledge graph visualization (`GraphCanvas`), we evaluated graph rendering libraries based on bundle impact, rendering performance for 300+ nodes, layout flexibility, and client-side DAG cycle prevention:

The implementation keeps the existing native Canvas renderer and force engine, so no graph dependency is added. Cytoscape.js and react-force-graph-2d provide more built-in graph features; d3-force provides a reusable simulation, but each would require an integration and a measured bundle comparison. The previous library size/FPS estimates were not benchmarks and have been removed.

Local verification of the integrated #108/#110 branch measured **50.5 FPS (week)** and **54.4 FPS (force)** while panning a synthetic graph with 300 nodes and 299 edges in headless Chrome, without CPU throttling. This is a development-machine sample, not proof of performance on a mid-range laptop. Main JavaScript gzip size was **120.20 KB**, compared with **106.53 KB** for `origin/main` (`350224d`) using the same installed toolchain: **+13.67 KB**. CSS gzip increased from 13.64 KB to 16.12 KB. Font assets were unchanged.

The force simulation pauses during background panning and resumes on release; rendering and viewport interaction continue every frame. The performance test is opt-in so concurrent browser suites do not distort it:

```powershell
$env:PLAYWRIGHT_CHANNEL = 'chrome'
$env:GRAPH_PERFORMANCE = '1'
pnpm --dir ui exec playwright test graph.spec.ts --project=backend-ui -g 'performance sample' --workers=1
Remove-Item Env:GRAPH_PERFORMANCE
```

Graph browser tests use explicit intercepted API fixtures to check integration contracts; they do not prove production persistence. The application uses the existing authenticated graph, local graph, edge and layout endpoints. Demo mode uses session storage for graph previews. Filters, layout choice and selected node use `kg_*` query parameters while preserving the app's route hash. Closing a panel keeps the selected node as the local-graph center. The list/filter region is scanned with axe on desktop and mobile; this is not an accessibility audit of the whole application.

### Technical Implementation:
- **Renderer**: Native HTML5 Canvas 2D with HiDPI scaling (`window.devicePixelRatio`).
- **Week Layout**: Deterministic syllabus column placement where $X = (\text{week} - 1) \times \text{colWidth}$ and $Y$ is distributed by topic sequence.
- **Force Layout**: Obsidian-style graph physics implementing Hooke's spring force on edges ($F_s = d^2/k$), Coulomb electrostatic repulsion between nodes ($F_r = k^2/d$), and center gravity attraction ($F_g = (c - p) \times \alpha$).
- **Client Cycle Prevention**: `findCyclePath()` performs iterative BFS from target to source before committing edges, preventing dependency loops and highlighting conflict paths in crimson red (`#ef4444`).
- **Interaction**: Zoom (wheel/touch/+/- keys, 0.2x–3.0x), background pan (drag/touch/arrows), node pin dragging (debounced `onLayoutChange`), and Shift+drag edge creation.


## Troubleshooting

- `node` or `npm` is not recognized: install Node.js 24 LTS, close the terminal, and open a new one.
- PowerShell reports that scripts are disabled: run `.\start.cmd` instead of `.\start.ps1`.
- PowerShell blocks `npm.ps1`: use `npm.cmd` or `npx.cmd` in place of `npm` or `npx`.
- `pnpm.cmd` is not recognized: use `npx.cmd --yes pnpm@11.25.0` in its place, from the `ui` folder. This runs the project's pinned pnpm version without a global installation; the first run needs internet access.
- Dependencies are missing: run `npm install` again in the `ui` folder.
- Port 5173 is busy: run `npm run dev -- --port 5174` and open the printed URL.
- To reset the demo: remove the `pathly.demo.v1` entry from the site's browser local storage.

## Try the workflows

The main navigation is the core loop only (spec 1.2): **Courses · Roadmap · Schedule · Library · Settings**. Supplementary pages keep their `#hash` routes (`#progress`, `#ai-reporter`, `#companion`) but open from a course or a step, not from the menu. Roadmap and Library (saved sources) are empty states until their screens land (#57, S8).

- Home: start a lesson, mark it studied, and pass its knowledge check. Reading does not award progress; passing the same session twice awards credit only once.
- Schedule: navigate weeks/months, return to Today, and select any session.
- Courses: try the local PDF upload and concept editor, then search/filter the sample library below it. Concept edits survive navigation between pages until reload. The proposed concepts are fixed Week 1 examples, not extracted from your uploaded PDF.
- Ask (from Home's "Plan in Ask"): try `learn Math 7`, `learn Physics`, `learn History 9`, `learn Biology 9`, `adjust workload`, or `weekly report`.
- Mastery opens from a goal under "Current goals" in the sidebar; Companion is a placeholder at `#companion`. Select the Pathly logo to return Home.
- Confirm the prerequisite, review the proposed plan, and approve enrollment. New sessions appear in the calendar. History starts at level 7; later levels remain conditional.
- Save a module to the future plan without adding sessions. Find it under Courses → Saved for later.
- Settings: change the display name and available weekly hours. Use Adjust workload to explicitly approve schedule changes.

## Prototype boundaries

No API keys, backend, database, or real LLM are needed. AI replies are deterministic examples, prerequisite confirmation is self-reported, schedule topics are sample data, and workload uses an illustrative 3 hours per active course estimate. Weekly budget adjustment resizes existing planned sessions (10–60 minutes), not a scheduling optimizer. English has four sample grammar questions; other modules use a clearly labeled workflow check. Mastery lists the scheduled demo sessions and updates each status after a passing check. The initial English goal begins with six example lessons already completed, plus seven scheduled sessions (6/13 verified).

State is stored under `pathly.demo.v1` in browser localStorage, not an account. Lesson scratch notes last only while the dialog is open. Removing that storage key resets the demo. Saved demo schedules are rebased when the date changes so the relative calendar remains usable.

## Code map

Two apps share one shell. `VITE_BACKEND_MODE=api` runs the real app; anything else runs the offline demo, which is a separate lazy chunk the real app never loads (`src/boundary.test.ts` fails if it starts to).

- `src/App.tsx`: picks the app by mode.
- `src/CoreApp.tsx`: the real app — Courses, Roadmap, Schedule (the scheduling workspace) and Library, all from the backend.
- `src/navigation.ts`: routes, labels, the main navigation and `useHashPage`; `#hash` ids never change, so bookmarks keep working.
- `src/components/`: `Shell` (sidebar, topbar, page heading, phone bottom bar), `Navigation`, buttons, accessible modal, progress meter.
- `src/pages/`: pages both apps use — Courses upload/concept editor (given a `CourseService`), Roadmap and Library empty states.
- `src/api/`: backend calls (`account.ts` sign-in, `courses.ts` course materials behind the `CourseService` interface), core-loop types (`types.ts`, checked against `docs/openapi.json` by `contract.test.ts`), and the learning-check adapter.
- `src/demo/`: everything demo-only — `DemoApp.tsx` (state and scripted coaching), its pages (Home, Schedule, Mastery, Ask, catalog), `model.ts`/`domain.ts` state and transitions, sample fixtures, fake sign-in, mock course service, lesson dialog and the local quiz adapter (not secure grading).
- `src/concepts.ts`: concept graph operations shared by both course services.
- `src/features/`: appearance settings and the asynchronous learning-check UI.
- `src/styles.css`: shared Figma colors, typography, cards, sidebar, responsive layouts.
- `src/**/*.test.*`, `e2e/`: unit/component tests (demo model invariants in `src/demo/model.test.ts`) and desktop/mobile browser regression tests.

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

See [frontend integration handoff](../docs/handoff-and-review/frontend-integration-handoff.md) for API examples,
reviewer names and roles, limitations, and the PR preparation checklist.

## Design source

https://www.figma.com/design/VG4biz9VR4o9dDg24Gl0BI

High-fidelity context was retrieved for Home, weekly Schedule, selected lesson, Library, course Progress, Reporter, Physics request, balanced proposal, History approval, overload warning, and deferred confirmation. Figma's Starter API limit prevented retrieval of some alternate states, including the monthly calendar; those interactions reuse the retrieved components. No screenshot is used as an implementation asset. The Code Connect `Book` component was not present in this Python starter, so the shared navigation uses the Library glyph supplied by the Home design. Inter is bundled locally through `@fontsource/inter`.

## Scheduling Workspace

Open `/#workspace` for the optional account-backed task planner. Start `assistant.backend.main:app` on port 8000 first. Workspace has its own account/session flow, separate from the course demo login. `VITE_API_URL` selects this scheduling backend; the course check API keeps its existing configuration. See [the scheduling handoff](../docs/handoff-and-review/minh-handoff.md).
